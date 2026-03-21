# GA4 Event Spec (Home Funnel)

This document describes the conversion funnel events emitted by:
- `/index.html`
- `/index-en.html`

## Base parameters (all events)

- `lang`: `es` or `en`
- `page_type`: `home`
- `source_page`: current pathname (`/` or `/en`)

## Events

1. `file_selected`
- Trigger: user selects a file from picker or drag-and-drop.
- Parameters:
  - `file_ext`: `docx`, `txt`, or `unknown`
  - `file_size_bucket`: `lt_100kb`, `100_500kb`, `500kb_1mb`, `1_3mb`, `3_5mb`

2. `convert_started`
- Trigger: submit handler starts conversion request.
- Parameters:
  - `file_ext`
  - `file_size_bucket`

3. `convert_success`
- Trigger: conversion request returns `2xx` and blob download flow starts.
- Parameters:
  - `file_ext`
  - `file_size_bucket`

4. `download_completed`
- Trigger: download link click is executed after successful conversion.
- Parameters:
  - `file_ext`
  - `file_size_bucket`

5. `convert_error`
- Trigger: conversion fails before or during request.
- Parameters:
  - `error_type`: `missing_file`, `network`, `http`
  - `http_status` (only when `error_type=http`)
  - `file_ext` and `file_size_bucket` when a file is present

## Anti-duplication notes

- Conversion is bound to `submit` only.
- Previous duplicate trigger (`click` + `submit`) is removed.
- `inFlight` guard prevents double submissions while one conversion is in progress.
