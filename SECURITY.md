# Security policy

## Declared service capability

Automatic popup selection inspects and restarts the existing user
`voxtype.service` while idle, after validating its daemon command and config
environment. It edits only Voxtype's `osd.enabled` preference through Voxtype's
own editor, saves the previous value for restoration, and never starts a stopped
service. See the README for manual setup and recovery.

The marketplace baseline classifies this as `review-required` for
`service-management`, even when there are no security findings. CI accepts only
that declared capability with evidence scoped to `voxtype.service` in the README
or backend. Every finding and unexpected capability still fails. The raw scan
classification is retained in CI logs and summaries; a successful CI run does
not replace marketplace human review or approval.

## Report a vulnerability privately

Please use [GitHub private vulnerability reporting](https://github.com/TechLuddite/luddite-voice-osd/security/advisories/new) for suspected security vulnerabilities in this project.

Do not disclose vulnerabilities, exploit details, credentials, or sensitive data in public issues or pull requests. Include the affected version or commit, potential impact, and minimal reproduction steps. Redact secrets and personal data, and test only systems you are authorized to access.

## Fixes and private collaboration

Proposed fixes are welcome. You may include patch/code details with your private report. If you would like to collaborate on a fix, say so in the report; the maintainer can arrange a temporary private fork through GitHub's security advisory workflow after triage. Please keep security-related code and discussion private until coordinated disclosure.

Reporting a vulnerability does not grant write access to this repository. Reports and proposed fixes are reviewed on a best-effort basis; no response deadline, fix guarantee, or bounty is promised.
