# Security policy

## Supported version

Security fixes target the latest `main` branch until the first stable release.

## Reporting

Please use GitHub's private vulnerability reporting for `pxnkit/evidroute`. Do not open a
public issue containing credentials, private benchmark content, exploitable trace payloads, or
personal data.

## Security boundaries

- Live web access is disabled by default.
- Private memory is not sent to external routes.
- Uploaded corpora remain local, are size- and type-limited, and are not indexed automatically.
- Retrieved text is untrusted data. Prompt-like instructions in evidence are detected and fail
  closed in the bundled safety scenarios.
- Serialized scikit-learn checkpoints are trusted local artifacts. Never load a checkpoint
  from an untrusted source because Python pickle is not a safe interchange format.

The prototype is not approved for medical, legal, financial, safety-critical, or production
decision-making.
