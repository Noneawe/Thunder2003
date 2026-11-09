# Theme packages

Each variant contains an installable colour-theme XPI, `userChrome.css`,
`userContent.css`, and the required `icons/` folder. Install all components
from the same variant. See the root [README](../README.md#installation).

Edit `gen/userChrome.template.css`, `gen/userContent.template.css`,
`gen/palettes.py`, and `gen/icons/` to change the design, then regenerate:

```bash
python3 -B Theme/gen/build.py
```

Run this command from the repository root. Generated files are committed
alongside their sources. The builder uses the existing Blue XPI manifest
as the metadata base, so keep that package in the repository.
