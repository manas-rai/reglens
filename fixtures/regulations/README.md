# Regulation Fixtures

Place regulatory PDF files here. The file is read verbatim and sent to the Gemini
multimodal ingestion agent.

## Example

Download an RBI Master Direction or circular (publicly available from rbi.org.in)
and place it here, e.g.:

```
fixtures/regulations/rbi_md_kyc_2016.pdf
```

Then start a run:

```bash
curl -X POST http://localhost:8000/runs \
  -H "x-api-key: $API_KEY" \
  -F "pdf=@fixtures/regulations/rbi_md_kyc_2016.pdf" \
  -F "matrix=@fixtures/control_matrices/banking.yaml" \
  -F "regulation_ref=RBI-MD-KYC-2016" \
  -F "domain=banking"
```
