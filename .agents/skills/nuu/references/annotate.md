# `annotate.py` Reference

`scripts/annotate.py` (or `nuu annotate`) renders boxes, arrows, labels, and callouts onto a PNG screenshot without overwriting the source image.

| Flag | Shorthand | Description |
| --- | --- | --- |
| `--input <png>` | `-i` | Source PNG screenshot path |
| `--output <png>` | `-o` | New destination PNG path |
| `--box <x,y,w,h[,color]>` | `-b` | Bounding box rectangle (repeatable) |
| `--label <x,y,text[,color]>` | `-l` | Text banner at `x,y` (repeatable) |
| `--arrow <x1,y1,x2,y2[,color]>` | `-a` | Arrow from `x1,y1` to `x2,y2` (repeatable) |
| `--callout <x,y,n[,label[,color]]>` | `-c` | Numbered badge at `x,y` (repeatable) |
| `--spec <json>` | `-s` | JSON file with `boxes`, `labels`, `arrows`, and `callouts` |
| `--json` | `-j` | Emit JSON output |
