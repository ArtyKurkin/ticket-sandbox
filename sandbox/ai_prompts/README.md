# AI Reviewer prompts

`TWC_AI_PROMPT_VERSION=v3` enables the repository-owned system prompt. The request
sends `v3.txt` as the system message and task/answer context as the user message.
The default remains v1; v1/v2 retain their single user message and agent settings.
No full v3 prompt needs to be copied into Fair Woodpecker settings.

Released prompt files are immutable: introduce `v4.txt` and explicit version
support for subsequent rule changes. Review records keep their selected version.
For v3, `AIReview.task_context._review_metadata` records `system_prompt_sha256`
(SHA256 of the exact UTF-8 file bytes) and `technical_check_passed` at submission.
The worker rejects a changed prompt hash before sending HTTP. No migration is needed.

Offline regression tests cover prompt rules, request construction, the JSON
contract and persistence with mocked HTTP. They do not measure a live model's
compliance; quality evaluation against a real agent is a separate operation.
