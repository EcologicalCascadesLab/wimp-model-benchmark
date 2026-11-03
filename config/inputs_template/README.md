# The four inputs for a benchmark

1. **Validated images**: a folder with one subfolder per class (`Blank/`, `Human/`, `Vehicle/`, `Thylogale stigmatica/` ...), or, if the images are already validated on WIMP, the name of the source project(s): `wimpbench select` then finds and downloads them.
2. **Project metadata** (`benchmark_projects.csv`): one row per model run: environment, project name, owner, and one location for the benchmark deployments.
3. **Image spreadsheet** (`validated_images.csv`): one row per image: file name, class, scientific name as used on WIMP, and where it came from. `select` writes this for you when images come from WIMP.
4. **Models to test** (`models.yaml`): classifier and detector threshold per run.

Guidance from Colin's workflow: aim for 100+ images per class, include blanks and the common non-target species (they drive precision), and avoid images used to train the model.
