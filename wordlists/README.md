# Wordlists

- `tiny_1k.txt` — bundled seed (~50 common passwords for testing)
- `small_10k.txt` — add your own top-10K list here

## Downloading larger wordlists

For `--tier large`, download rockyou.txt from SecLists or similar:

```
https://github.com/danielmiessler/SecLists/blob/master/Passwords/Leaked-Databases/rockyou.txt.tar.gz
```

Then use `--wordlist path/to/rockyou.txt` or place it as `wordlists/large.txt`.
