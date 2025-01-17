#!/bin/bash

echo ">> [1] Collecting codes..."
python workflow/01_arxiv_codes.py
echo ">> [2] Collecting citations..."
python workflow/02_semantic_citations.py
echo ">> [3] Processing content..."
python workflow/03_arxiv_content.py
echo ">> [4] Running topic model..."
python workflow/04_topics.py
echo ">> [5] Updating Gist catalogue..."
python workflow/05_gist_catalogue.py
echo ">> [6] Linking thumbnails..."
python workflow/06_img_processor.py

echo "Done! Please enjoy the rest of your day and spread love around your neighbourhood."