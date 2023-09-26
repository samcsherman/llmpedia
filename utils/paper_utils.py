import os
import re, json
import arxiv
import requests
import psycopg2
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from sqlalchemy import create_engine
from concurrent.futures import ThreadPoolExecutor

from langchain.document_loaders import ArxivLoader


PROJECT_PATH = os.environ.get("PROJECT_PATH")

db_params = {
    "dbname": os.environ["DB_NAME"],
    "user": os.environ["DB_USER"],
    "password": os.environ["DB_PASS"],
    "host": os.environ["DB_HOST"],
    "port": os.environ["DB_PORT"],
}

summary_col_mapping = {
    "arxiv_code": "arxiv_code",
    "main_contribution_headline": "contribution_title",
    "main_contribution_description": "contribution_content",
    "takeaways_headline": "takeaway_title",
    "takeaways_description": "takeaway_content",
    "takeaways_example": "takeaway_example",
    "category": "category",
    "novelty_score": "novelty_score",
    "novelty_analysis": "novelty_analysis",
    "technical_score": "technical_score",
    "technical_analysis": "technical_analysis",
    "enjoyable_score": "enjoyable_score",
    "enjoyable_analysis": "enjoyable_analysis",
}


vectorizer = TfidfVectorizer(analyzer="char", ngram_range=(2, 3), use_idf=False)


def store_local(data, arxiv_code, data_path, relative=True, format="json"):
    """Store data locally."""
    if relative:
        data_path = os.path.join(PROJECT_PATH, data_path)
    if format == "json":
        with open(os.path.join(data_path, f"{arxiv_code}.json"), "w") as f:
            json.dump(data, f)
    elif format == "txt":
        with open(os.path.join(data_path, f"{arxiv_code}.txt"), "w") as f:
            f.write(data)
    else:
        raise ValueError("Format not supported.")


def load_local(arxiv_code, data_path, relative=True, format="json"):
    """Load data locally."""
    if relative:
        data_path = os.path.join(PROJECT_PATH, data_path)
    if format == "json":
        with open(os.path.join(data_path, f"{arxiv_code}.json"), "r") as f:
            return json.load(f)
    elif format == "txt":
        with open(os.path.join(data_path, f"{arxiv_code}.txt"), "r") as f:
            return f.read()
    else:
        raise ValueError("Format not supported.")


def search_arxiv_doc(paper_name):
    """Search for a paper in Arxiv and return the most similar one."""
    docs = ArxivLoader(
        query=preprocess(paper_name),
        doc_content_chars_max=70000,
        load_all_available_meta=True,
        load_max_docs=2,
    ).load()

    if len(docs) == 0:
        return None

    docs = sorted(
        docs,
        key=lambda x: tfidf_similarity(paper_name, x.metadata["Title"]),
        reverse=True,
    )
    new_title = docs[0].metadata["Title"]
    title_sim = tfidf_similarity(paper_name, new_title)
    if title_sim < 0.7:
        print(f"No similar title name found for {paper_name}.")
        return None

    return docs[0]


def preprocess_arxiv_doc(doc, token_encoder=None):
    """Preprocess an Arxiv document."""
    doc_content = reformat_text(doc.page_content)
    if len(doc_content.split("References")) == 2:
        doc_content = doc_content.split("References")[0]

    if token_encoder:
        ntokens_doc = len(token_encoder.encode(doc_content))
        if ntokens_doc > 12000:
            doc_content = doc_content[:int(12000*3.2)]

    return doc_content


def reformat_text(doc_content):
    """Clean and simplify text string."""
    content = doc_content.replace("-\n", "")
    content = re.sub(r"(?<!\n)\n(?!\n)", " ", content)
    content = re.sub(" +", " ", content)
    return content


def preprocess(text):
    """Clean and simplify text string."""
    text = "".join(c.lower() if c.isalnum() else " " for c in text)
    return text


def flatten_dict(d, parent_key="", sep="_"):
    """Flatten a nested dictionary."""
    items = {}
    for k, v in d.items():
        new_key = parent_key + sep + k if parent_key else k
        if isinstance(v, dict):
            items.update(flatten_dict(v, new_key, sep=sep))
        else:
            items[new_key] = v
    return items


def transform_flat_dict(flat_data, mapping):
    """Rename and drop columns from a flattened dictionary."""
    return {mapping[k]: flat_data[k] for k in mapping if k in flat_data}


def tfidf_similarity(title1, title2, fitted=False):
    """Compute cosine similarity of TF-IDF representation between 2 strings."""
    title1 = preprocess(title1)
    title2 = preprocess(title2)
    if not fitted:
        vectors = vectorizer.fit_transform([title1, title2])
    else:
        vectors = vectorizer.transform([title1, title2])
    return cosine_similarity(vectors[0:1], vectors[1:2])[0][0]


def compute_optimized_similarity(data_title, titles):
    """ Multithreading TF-IDF similarity computation. """
    with ThreadPoolExecutor() as executor:
        futures = [
            executor.submit(tfidf_similarity, data_title, title, True)
            for title in titles
        ]
    return [future.result() for future in futures]


def get_arxiv_info(arxiv_code, title):
    """Search article in Arxiv by name and retrieve meta-data."""
    search = arxiv.Search(
        query=arxiv_code, max_results=40, sort_by=arxiv.SortCriterion.Relevance
    )
    res = list(search.results())
    if len(res) > 0:
        ## Sort by title similarity.
        res = sorted(res, key=lambda x: tfidf_similarity(title, x.title), reverse=True)
        new_title = res[0].title
        title_sim = tfidf_similarity(title, new_title)
        if title_sim > 0.7:
            return res[0]
        else:
            return None
    return None


def process_arxiv_data(data):
    """Transform the arxiv data for database insertion."""
    data = {k.lower(): v for k, v in data.items()}
    flat_data = flatten_dict(data)
    desired_fields = [
        "id",
        "updated",
        "published",
        "title",
        "summary",
        "authors",
        "arxiv_comment",
    ]
    filtered_data = {k: flat_data[k] for k in desired_fields if k in flat_data}
    filtered_data["arxiv_code"] = filtered_data.pop("id").split("/")[-1].split("v")[0]
    author_names = [author["name"] for author in filtered_data["authors"]]
    filtered_data["authors"] = ", ".join(author_names)
    filtered_data["authors"] = filtered_data["authors"][:1000]
    filtered_data["title"] = filtered_data["title"].replace("\n ", "")
    filtered_data["summary"] = filtered_data["summary"].replace("\n", " ")
    if "arxiv_comment" in filtered_data:
        filtered_data["arxiv_comment"] = filtered_data["arxiv_comment"].replace(
            "\n ", ""
        )
    return filtered_data


def get_semantic_scholar_info(arxiv_code):
    """Search article in Semantic Scholar by Arxiv code and retrieve meta-data."""
    url = f"https://api.semanticscholar.org/graph/v1/paper/ARXIV:{arxiv_code}?fields=title,citationCount,influentialCitationCount,tldr,venue"
    response = requests.get(url)
    if response.status_code == 200:
        return response.json()
    else:
        return None


################
## DB RELATED ##
################
def check_in_db(arxiv_code, db_params, table_name):
    """Check if an arxiv code is in the database."""
    with psycopg2.connect(**db_params) as conn:
        with conn.cursor() as cur:
            cur.execute(f"SELECT * FROM {table_name} WHERE arxiv_code = '{arxiv_code}'")
            return bool(cur.rowcount)


def upload_to_db(data, db_params, table_name):
    """Upload a dictionary to a database."""
    with psycopg2.connect(**db_params) as conn:
        with conn.cursor() as cur:
            columns = ", ".join(data.keys())
            placeholders = ", ".join(["%s"] * len(data))
            cur.execute(
                f"INSERT INTO {table_name} ({columns}) VALUES ({placeholders})",
                list(data.values()),
            )


def remove_from_db(arxiv_code, db_params, table_name):
    """Remove an entry from the database."""
    with psycopg2.connect(**db_params) as conn:
        with conn.cursor() as cur:
            cur.execute(f"DELETE FROM {table_name} WHERE arxiv_code = '{arxiv_code}'")


def upload_df_to_db(df, table_name, params):
    """Upload a dataframe to a database."""
    db_url = (
        f"postgresql+psycopg2://{params['user']}:{params['password']}"
        f"@{params['host']}:{params['port']}/{params['dbname']}"
    )
    engine = create_engine(db_url)
    df.to_sql(
        table_name, engine, if_exists="append", index=False, method="multi", chunksize=10
    )

    ## Commit.
    with psycopg2.connect(**params) as conn:
        with conn.cursor() as cur:
            cur.execute("COMMIT")
    return True


def get_arxiv_id_list(db_params, table_name):
    """Get a list of all arxiv codes in the database."""
    with psycopg2.connect(**db_params) as conn:
        with conn.cursor() as cur:
            cur.execute(f"SELECT DISTINCT arxiv_code FROM {table_name}")
            return [row[0] for row in cur.fetchall()]


def get_arxiv_title_dict(db_params=db_params):
    """Get a list of all arxiv titles in the database."""
    with psycopg2.connect(**db_params) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
            SELECT a.arxiv_code, a.title 
            FROM arxiv_details a
            RIGHT JOIN summaries s ON a.arxiv_code = s.arxiv_code
            WHERE a.title IS NOT NULL
            """
            )
            title_map = {row[0]: row[1] for row in cur.fetchall()}
            return title_map


##################
## GIST RELATED ##
##################
def fetch_queue_gist(gist_id, gist_filename="llm_queue.txt"):
    """Fetch the queue of papers to be reviewed from a GitHub gist."""
    response = requests.get(f"https://api.github.com/gists/{gist_id}")
    paper_list = None

    if response.status_code == 200:
        gist = response.json()
        paper_url = gist["files"][gist_filename]["raw_url"]
        response = requests.get(paper_url)
        if response.status_code == 200:
            paper_list = response.text.split("\n")
            paper_list = [p.strip() for p in paper_list if len(p.strip()) > 0]

    return paper_list


def update_gist(
    token: str,
    gist_id: str,
    gist_filename: str,
    gist_description: str,
    gist_content: str,
):
    """Upload a text file as a GitHub gist."""
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json",
    }
    params = {
        "description": gist_description,
        "files": {gist_filename: {"content": gist_content}},
    }
    response = requests.patch(
        f"https://api.github.com/gists/{gist_id}",
        headers=headers,
        data=json.dumps(params),
    )

    if response.status_code == 200:
        print(f"Gist {gist_filename} updated successfully.")
        return response.json()["html_url"]
    else:
        print(f"Failed to update gist. Status code: {response.status_code}.")
        return None