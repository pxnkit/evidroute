# Paper scaffold

`main.tex` is a transparent manuscript scaffold, not an accepted or submitted paper. It states
which experiments are complete and leaves public benchmark tables explicitly unrun.

Build with:

```bash
latexmk -pdf -interaction=nonstopmode main.tex
```

Generated MiniRoute assets originate from raw predictions under `artifacts/`. Do not replace
placeholder public benchmark cells with estimates or invented numbers.
