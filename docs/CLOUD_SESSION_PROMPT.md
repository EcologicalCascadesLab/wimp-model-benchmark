# Starting a cloud session on this repository

## One-time environment setup (claude.ai/code -> environment settings)

- **Network access:** Custom, allowing `api.wimp.wildobs.org.au`,
  `api.wimp.test.wildobs.org.au`, `media.wimp.wildobs.org.au`,
  `media.wimp.test.wildobs.org.au` (keep the default package registries ticked).
- **Environment variables:** `WIMP_PROD_KEY` and `WIMP_TEST_KEY` (WIMP > User
  settings > API keys). Never put them in the repository.
- **Setup script:** `pip install -r requirements.txt && git submodule update --init`

## Prompt to paste (image-level run)

> Do the task in docs/TASK_by_image.md, following CLAUDE.md. Start with step 0 and stop
> if anything fails. Push every finished step straight to main.
