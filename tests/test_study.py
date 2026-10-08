import csv
import json
import numpy as np
import pytest
import soundfile as sf

from evaluation.study import (
    prepare,
    read_judgments,
    evaluate_judgments,
    render_hard_cut,
    boundary_metrics,
)
from tests.test_artifacts import catalog


def test_preparation_leaves_judgments_blank_and_requires_independent_evidence(tmp_path):
    c = catalog()
    prepare(tmp_path, c)
    manifest = json.loads((tmp_path / "study_manifest.json").read_text())
    assert not manifest["judgments_collected"] and manifest["rating_fields_are_blank"]
    assert read_judgments(tmp_path / "song_judgments.csv") == []
    assert (
        evaluate_judgments(c, tmp_path / "song_judgments.csv")["status"]
        == "NO_JUDGMENTS"
    )
    with (tmp_path / "song_judgments.csv").open(newline="") as f:
        rows = list(csv.DictReader(f))
        fields = list(rows[0])
    rows[0]["session_acceptance"] = "yes"
    with (tmp_path / "song_judgments.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    with pytest.raises(ValueError, match="consent"):
        read_judgments(tmp_path / "song_judgments.csv")


def test_actual_hard_cut_boundaries_and_metrics_with_synthetic_licensed_tones(tmp_path):
    sr = 22050
    a = np.full(sr, 0.2)
    b = np.full(sr, 0.1)
    sf.write(tmp_path / "a.wav", a, sr, subtype="FLOAT")
    sf.write(tmp_path / "b.wav", b, sr, subtype="FLOAT")
    metadata = render_hard_cut(
        tmp_path / "a.wav", tmp_path / "b.wav", tmp_path / "cut.wav", seconds=0.5
    )
    audio, out_sr = sf.read(tmp_path / "cut.wav")
    assert out_sr == sr and len(audio) == sr
    assert metadata["cut_sample"] == sr // 2
    assert np.mean(audio[: sr // 2]) == pytest.approx(0.2, abs=1e-4)
    assert np.mean(audio[sr // 2 :]) == pytest.approx(0.1, abs=1e-4)
    assert metadata["loudness_jump_db"] == pytest.approx(-6.0206, abs=1e-3)
    silence = np.r_[np.zeros(sr // 2), np.ones(sr // 2) * 0.2]
    assert boundary_metrics(silence, sr)["leading_silence_seconds"] == pytest.approx(
        0.5
    )
