import base64
from io import BytesIO
from os import makedirs
from typing import Dict, List

import matplotlib.pyplot as plt
import pandas as pd
import requests
from dagster import AssetExecutionContext, MetadataValue, asset


@asset(
    io_manager_key="database_io_manager",
)
def topstory_ids(context: AssetExecutionContext) -> pd.DataFrame:
    newstories_url = "https://hacker-news.firebaseio.com/v0/topstories.json"
    top_new_story_ids = requests.get(newstories_url).json()[:10]

    context.add_output_metadata(
        metadata={
            "num_records": len(top_new_story_ids),
        }
    )
    return pd.DataFrame(top_new_story_ids, columns=["top_new_story_id"])


@asset(
    io_manager_key="database_io_manager",
)
def topstories(
    context: AssetExecutionContext, topstory_ids: pd.DataFrame
) -> pd.DataFrame:
    ids = topstory_ids["top_new_story_id"]

    results = []
    for item_id in ids:
        item = requests.get(
            f"https://hacker-news.firebaseio.com/v0/item/{item_id}.json"
        ).json()
        results.append(item)

        if len(results) % 10 == 0:
            context.log.info(f"Got {len(results)} items so far.")

    df = pd.DataFrame(results)
    context.add_output_metadata(
        metadata={
            "num_records": len(df),
            "preview": MetadataValue.md(df.head().to_markdown() or ""),
        }
    )
    return df


@asset
def most_frequent_words(
    context: AssetExecutionContext, topstories: pd.DataFrame
) -> Dict:
    stopwords = ["a", "the", "an", "of", "to", "in", "for", "and", "with", "on", "is"]

    # NOTE: I/Oマネージャー使うと自前でファイルを保存しなくてもいい
    # topstories = pd.read_csv("data/topstories.csv")

    # loop through the titles and count the frequency of each word
    word_counts = {}
    for raw_title in topstories["title"]:
        title = raw_title.lower()
        for word in title.split():
            cleaned_word = word.strip(".,-!?:;()[]'\"-")
            if cleaned_word not in stopwords and len(cleaned_word) > 0:
                word_counts[cleaned_word] = word_counts.get(cleaned_word, 0) + 1

    # Get the top 25 most frequent words
    top_words = {
        pair[0]: pair[1]
        for pair in sorted(word_counts.items(), key=lambda x: x[1], reverse=True)[:25]
    }

    # Make a bar chart of the top 25 words
    plt.figure(figsize=(10, 6))
    plt.bar(list(top_words.keys()), list(top_words.values()))
    plt.xticks(rotation=45, ha="right")
    plt.title("Top 25 Words in Hacker News Titles")
    plt.tight_layout()

    # Convert the image to a saveable format
    buffer = BytesIO()
    plt.savefig(buffer, format="png")
    image_data = base64.b64encode(buffer.getvalue())

    # Convert the image to Markdown to preview it within Dagster
    md_content = f"![img](data:image/png;base64,{image_data.decode()})"

    # I/Oマネージャー使うと自前でファイルを保存しなくてもいい
    # with open("data/most_frequent_words.json", "w") as f:
    #     json.dump(top_words, f)

    context.add_output_metadata(
        metadata={"plot": MetadataValue.md(md_content)},
    )

    return top_words
