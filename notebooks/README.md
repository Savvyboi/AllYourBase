# Colab processing runtime

The owner selected Google Colab for processing on 2026-10-14. The package and CLI
remain the implementation; notebooks only install verified source, load secrets,
call commands and archive completed evidence.

## Phase 1 optical validation

Open `phase-1-cdse-optical.ipynb` in Colab using **File > Upload notebook**.
Use a CPU runtime. Upload the matching `allyourbase-colab-source.zip` when prompted.
The notebook checks the ZIP SHA-256 before installing its locked Python 3.12
access environment. The archive's source manifest records each file hash and the
base Git revision, including working-tree changes by their exact hashes.

Create the separate S3 keys at the
[CDSE S3 key manager](https://eodata-s3keysmanager.dataspace.copernicus.eu/).
Choose an expiry date and save the secret when it is displayed; it is shown once.
In Colab's **Secrets** sidebar add `CDSE_S3_ACCESS_KEY_ID` and
`CDSE_S3_SECRET_ACCESS_KEY`, then enable notebook access. Never paste values in
cells, chat or source files. OAuth keys are separate and unnecessary for this run.
[CDSE setup reference](https://documentation.dataspace.copernicus.eu/APIs/S3.html)
and [Colab Secrets API](https://github.com/googlecolab/colabtools/blob/main/google/colab/userdata.py).

Run cells in order. The pinned check selects only `cdse_stac`, eight complete
weeks ending at 2026-W41, the three already-approved areas and `--pixels`.
It makes no radar Process requests. The saved files are independently verified
by `providers validate-optical`; acceptance requires three sites and 21 files.
Download the evidence ZIP before disconnecting, or enable the optional completed
archive copy to Drive. Colab's VM files are temporary; see the
[Colab FAQ](https://research.google.com/colaboratory/faq.html).

The notebook preserves failed reports for review and never claims fallback
success from credential presence or metadata alone. It writes only completed,
uniquely named archives to Drive, with a hash check and temporary-file rename.
It does not place a live database on Drive.

To regenerate the source bundle after changing included source files:

```sh
uv run python scripts/export_colab_source.py --output ../phase1-data/colab/allyourbase-colab-source.zip
```

Replace the notebook's `SOURCE_SHA256` with the reported ZIP hash. Notebook
outputs must be cleared before committing or sharing it. Do not include data,
credentials, a virtual environment or Git metadata in the source archive.

## Verified pilot run

The Colab run `20261013T234356Z-1737c37ff296467c979cd05e9ab00b63` passed on
2026-10-14: all 21 band files, eight complete weeks and three approved areas.
Independent local verification exactly matches the Colab summary and the source
manifest matches the delivered bundle. See [the live evidence record](../docs/phase-1-live-validation.md).
Keep that original notebook/bundle pair with its matching source hash for
reproducibility; regenerate a matched pair if source files change.

## Full processing is pending

This notebook is a bounded Phase 1 access check. Phase 7a still needs the resumable
results store, VM-local database, checkpoint sync and shared one-writer lock.
Acceptance still requires interruption/resume and overlapping-writer tests.
Choosing Colab does not mark these later capabilities complete.
