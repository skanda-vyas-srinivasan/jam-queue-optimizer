from __future__ import annotations

from pathlib import Path

import pandas as pd
import plotly.express as px
from sklearn.decomposition import PCA

from .catalog import SongCatalog
from .paths import ARTIFACT_DIR


def build_embedding_frame(catalog: SongCatalog, n_components: int = 3) -> pd.DataFrame:
    return build_embedding_frame_for_space(catalog, space="raw", n_components=n_components)


def build_embedding_frame_for_space(
    catalog: SongCatalog,
    space: str = "raw",
    n_components: int = 3,
) -> pd.DataFrame:
    if n_components != 3:
        raise ValueError("The current plotter expects exactly 3 PCA components")

    if space == "raw":
        matrix = catalog.embeddings
    elif space == "normalized":
        matrix = catalog.normalized_embeddings
    else:
        raise ValueError(f"Unknown embedding space: {space}")

    coords = PCA(n_components=n_components).fit_transform(matrix)
    return pd.DataFrame(
        {
            "song": catalog.names,
            "folder": catalog.folders,
            "x": coords[:, 0],
            "y": coords[:, 1],
            "z": coords[:, 2],
        }
    )


def save_embedding_plot(
    catalog: SongCatalog,
    output_path: Path | str = ARTIFACT_DIR / "song_embedding_plot.html",
    space: str = "raw",
) -> Path:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df = build_embedding_frame_for_space(catalog, space=space)
    fig = px.scatter_3d(
        df,
        x="x",
        y="y",
        z="z",
        color="folder",
        hover_name="song",
        title=f"Song Embedding Space ({space})",
    )
    fig.write_html(output_path)
    return output_path
