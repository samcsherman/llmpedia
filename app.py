import streamlit as st
import plotly.graph_objects as go
import plotly.express as px
from streamlit_plotly_events import plotly_events

from typing import Dict, List, Tuple
import pandas as pd
import numpy as np
import psycopg2
import json
import re, os

import plotly.io as pio

pio.templates.default = "plotly"

## Page config.
st.set_page_config(
    layout="wide",
    page_title="📚 Regulatory Comments Explorer",
    page_icon="📚",
    initial_sidebar_state="expanded",
)

if "papers" not in st.session_state:
    st.session_state.papers = None

if "page_number" not in st.session_state:
    st.session_state.page_number = 0

if "num_pages" not in st.session_state:
    st.session_state.num_pages = 0

if "arxiv_code" not in st.session_state:
    st.session_state.arxiv_code = ""

st.markdown(
    """
    <style>
        @import 'https://fonts.googleapis.com/css2?family=Orbitron&display=swap';
        .pixel-font {
            font-family: 'Roboto', sans-serif;
            font-size: 32px;
            margin-bottom: 1rem;
        }
    </style>
""",
    unsafe_allow_html=True,
)

# @st.cache_data
def load_data():
    """Load data from compiled dataframe."""
    result_df = pd.read_csv("streamlit_data2.csv")

    return result_df


def create_paper_card(paper: Dict, mode="preview"):
    """Creates card UI for paper details."""
    img_cols = st.columns((1, 3))
    expanded = False
    if mode == "open":
        expanded = True
    summary = paper["summary"]
    paper_title = paper["company"]

    st.title(f':blue[{paper_title}]')
    # img_cols[1].markdown(
    #     f'<h2><a href="{paper_title}" style="color: #FF4B4B;">{paper_title}</a></h2>',
    #     unsafe_allow_html=True,
    # )
    # with st.expander(f"{paper_title} - - A Short Summary", expanded=expanded):
    #     st.markdown(paper['short_summary'])

    with st.expander(f"{paper_title} - - A Summary", expanded=expanded):
        st.markdown(summary)

    with st.expander(f"Sentiment Analysis", expanded=expanded):
        st.markdown(f"{paper['sentiment_explanation']}")

    with st.expander(
        f"Summary Validation", expanded=expanded):
        st.markdown(f"{paper['summary_validation']}")

    with st.expander(
        f"Original Comment", expanded=expanded):
        # paper['text'] = paper['text']
        st.markdown(f"{str(paper['text'])}")

    st.markdown("---")

#
# def generate_grid_gallery(df, n_cols=3):
#     """Create streamlit grid gallery of paper cards with thumbnail."""
#     n_rows = int(np.ceil(len(df) / n_cols))
#     for i in range(n_rows):
#         cols = st.columns(n_cols)
#         for j in range(n_cols):
#             if i * n_cols + j < len(df):
#                 with cols[j]:
#                     paper_title = df.iloc[i * n_cols + j]["company"] + "\nA Summary from ChatGPT"
#                     st.markdown(
#                         f'{paper_title}',
#                     )
#                     paper_code = df.iloc[i * n_cols + j].name
#                     focus_btn = st.button(
#                         "Read Summary", use_container_width=True
#                     )
#                     if focus_btn:
#                         st.session_state.arxiv_code = paper_code
#                         click_tab(3)
#                     # star_count = df.iloc[i * n_cols + j]["influential_citation_count"] > 0
#                     # publish_date = pd.to_datetime(
#                     #     df.iloc[i * n_cols + j]["published"]
#                     # ).strftime("%B %d, %Y")
#                     # star = ""
#                     # if star_count:
#                     #     star = "⭐️"
#                     # st.code(f"{star} {publish_date}", language="html")
#                     # last_updated = pd.to_datetime(
#                     #     df.iloc[i * n_cols + j]["published"]
#                     # ).strftime("%B %d, %Y")
#                     # # st.markdown(f"{last_updated}")
#                     # authors_str = df.iloc[i * n_cols + j]["authors"]
#                     # authors_str = (
#                     #     authors_str[:30] + "..."
#                     #     if len(authors_str) > 30
#                     #     else authors_str
#                     # )
#                     # st.markdown(authors_str)


def create_pagination(items, items_per_page, label="summaries"):
    num_items = len(items)
    num_pages = num_items // items_per_page
    if num_items % items_per_page != 0:
        num_pages += 1

    st.session_state["num_pages"] = num_pages

    st.markdown(f"**Pg. {st.session_state.page_number + 1} of {num_pages}**")
    prev_button, mid, next_button = st.columns((1, 10, 1))
    prev_clicked = prev_button.button("Prev", key=f"prev_{label}")
    next_clicked = next_button.button("Next", key=f"next_{label}")

    if prev_clicked and "page_number" in st.session_state:
        st.session_state.page_number = max(0, st.session_state.page_number - 1)
        st.experimental_rerun()
    if next_clicked and "page_number" in st.session_state:
        st.session_state.page_number = min(
            num_pages - 1, st.session_state.page_number + 1
        )
        st.experimental_rerun()

    start_index = st.session_state.page_number * items_per_page
    end_index = min(start_index + items_per_page, num_items)

    return items[start_index:end_index]


def create_bottom_navigation(label):
    num_pages = st.session_state["num_pages"]
    st.write(f"**Pg. {st.session_state.page_number + 1} of {num_pages}**")
    prev_button_btm, _, next_button_btm = st.columns((1, 10, 1))
    prev_clicked_btm = prev_button_btm.button("Prev", key=f"prev_{label}_btm")
    next_clicked_btm = next_button_btm.button("Next", key=f"next_{label}_btm")
    if prev_clicked_btm and "page_number" in st.session_state:
        st.session_state.page_number = max(0, st.session_state.page_number - 1)
        st.experimental_rerun()
    if next_clicked_btm and "page_number" in st.session_state:
        st.session_state.page_number = min(
            num_pages - 1, st.session_state.page_number + 1
        )
        st.experimental_rerun()


def click_tab(tab_num):
    js = f"""
    <script>
        var tabs = window.parent.document.querySelectorAll("[id^='tabs-bui'][id$='-tab-{tab_num}']");
        if (tabs.length > 0) {{
            tabs[0].click();
        }}
    </script>
    """
    st.components.v1.html(js)


def main():

    st.markdown(
        """<div class="pixel-font">Regulatory Comment Explorer</div>
    """,
        unsafe_allow_html=True,
    )
    st.markdown(
        "##### Comment Summaries from the proposed rule EPA-HQ-OAR-2023-0234"
    )
    ## Humorous and poetic introduction.
    st.markdown(
        "For the given docket-id, comments submitted are summarized and put through a sentiment analysis by ChatGPT.\n" 
        "Please use this app to find any summaries of interest. You can sort and filter. It may be particularly useful\n"
        "to sort by `Sentiment Score` or filter by `Company`."
    )

    ## Main content.
    data = load_data()
    st.session_state["paper"] = data

    ## Filter sidebar.
    st.sidebar.markdown("# 📁 Filters")
    company = st.sidebar.multiselect(
        "Company Filter",
        list(data["company"].unique()),
    )

    ## Sort by.
    sort_by = st.sidebar.selectbox(
        "Sort By",
        ["Company", "Sentiment Score Ascending", "Sentiment Score Descending"],
    )

    ## Company Filter.
    if len(company) > 0:
        data = data[data["company"].isin(company)]

    ## Order.
    if sort_by == "Company":
        data = data.sort_values("company", ascending=True)
    elif sort_by == "Sentiment Score Descending":
        data = data.sort_values("sentiment_score", ascending=False)
    elif sort_by == "Sentiment Score Ascending":
        data = data.sort_values("sentiment_score", ascending=True)

    papers = data.to_dict("records")

    # ## Content tabs.
    # content_tabs = st.tabs(["Feed View"])

    # with content_tabs[0]:
    if "page_number" not in st.session_state:
        st.session_state.page_number = 0

    papers_subset = create_pagination(papers, items_per_page=7, label="summaries")
    for paper in papers_subset:
        create_paper_card(paper)
    create_bottom_navigation(label="summaries")



if __name__ == "__main__":
    main()
