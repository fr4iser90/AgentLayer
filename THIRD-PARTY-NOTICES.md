# Third-party notices

AgentLayer itself is MIT-licensed (see `LICENSE`). This file covers bundled
third-party material whose license asks to be reproduced when the software is
redistributed.

## IBM Plex Sans / IBM Plex Mono

| | |
|---|---|
| Component | `apps/frontend/public/fonts/ibm-plex-sans-latin-400.woff2` |
| | `apps/frontend/public/fonts/ibm-plex-sans-latin-600.woff2` |
| | `apps/frontend/public/fonts/ibm-plex-mono-latin-400.woff2` |
| Copyright | Copyright © 2017 IBM Corp. with Reserved Font Name "Plex" |
| License | SIL Open Font License 1.1 |
| Full license text | `apps/frontend/public/fonts/OFL.txt` (shipped alongside the fonts, served at `/app/fonts/OFL.txt`) |
| Source | `@fontsource/ibm-plex-sans@5.2.5`, `@fontsource/ibm-plex-mono@5.2.5` via jsDelivr |
| Modifications | None to the font software. Files are renamed (`ibm-plex-sans-latin-400-normal.woff2` → `ibm-plex-sans-latin-400.woff2`); byte content is unchanged. |

Verified hashes (SHA-256):

```
3b646991d30055a93a4ecc499713d4347953a74a947ecab435ab72070cbdab0e  ibm-plex-sans-latin-400.woff2
8960851d691c054ed38e259bdcf1a6190d157b4203ed5bb32c632a863fb8ec2f  ibm-plex-sans-latin-600.woff2
3c5a451f9ec27a354b0c2bcca636c6ec17a651281aabf29f8427e210a1d31e85  ibm-plex-mono-latin-400.woff2
```

### Why a text file rather than in-font metadata

The latin subsets carry no name or licence records — `strings` finds zero
occurrences of "Plex", "SIL" or the licence URL inside the three `.woff2`
files. OFL 1.1 condition 2 requires every distributed copy to carry the
copyright notice and the licence, and offers stand-alone text files as the
vehicle when a metadata field is not available. Hence `OFL.txt` next to the
fonts.

Because the fonts ship in `apps/frontend/public/`, Vite copies them verbatim
into `dist/`, and the Dockerfile copies `dist/` into the runtime image, the
licence travels with every distributed copy and stays readable by a user at
`/app/fonts/OFL.txt` without needing to open the repository.

### OFL obligations that apply to us

- **C2** — bundled copies must carry the notice and licence. Satisfied by
  `apps/frontend/public/fonts/OFL.txt`.
- **C1** — the fonts may not be sold by themselves. They are only ever shipped
  inside AgentLayer.
- **C3** — the Reserved Font Name "Plex" may not be used for a modified
  version. We distribute the fonts unmodified, so the name stays accurate. If
  a future change re-subsets, re-instruments or otherwise alters glyph data,
  the result must be renamed before distribution.
- **C4** — IBM's name is not used to promote AgentLayer.
