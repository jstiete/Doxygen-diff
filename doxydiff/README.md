# doxydiff

`doxydiff` compares the **Doxygen documentation** of two versions of a
software project (e.g. two git tags/branches, or two checked-out folders)
and produces a single, self-contained **git-diff style HTML report**:

- red/green, word- and line-level highlighting of changed brief/detailed
  descriptions, markdown pages, titles and signatures (like `git diff`)
- detection of **added / removed / modified / moved** classes, structs,
  namespaces, files, directories, pages, groups, functions, variables, ...
- **image diffs** (e.g. logos, screenshots) with the changed region outlined
  in red, using OpenCV
- **call-graph / caller-graph / inheritance-graph diffs** that are robust
  against layout shifts: adding one function does not make the whole graph
  look "different" - only the genuinely new/removed nodes and edges are
  reported and highlighted
- a **top overview table** of every difference, with counts and links that
  jump straight to the detailed diff, plus summary statistics (objects
  added/removed/modified/moved, doc lines added/removed) that can be used to
  spot regressions (e.g. "a lot of documentation just disappeared") between
  CI runs

The comparison works on Doxygen's **XML output**, not the HTML output,
because the XML is structured and can be matched by the *qualified name* of
each element instead of by (unstable) file position - see
["Why compare the XML output"](#why-compare-the-xml-output-and-not-html)
below. When the real Doxygen HTML output directories are also passed in,
every compound/member/image/graph in the report additionally gets **"view
in v1 docs" / "view in v2 docs" links** straight into the corresponding
page (and, for members and member-level call/caller graphs, the exact
anchor) of Doxygen's own generated HTML, for convenient browsing.

## Contents

- [How it works](#how-it-works)
- [Requirements](#requirements)
- [Required Doxyfile settings](#required-doxyfile-settings)
- [Installation](#installation)
- [Usage](#usage)
- [Linking into the real Doxygen HTML output](#linking-into-the-real-doxygen-html-output)
- [CI / regression checks](#ci--regression-checks)
- [Demo project used for testing](#demo-project-used-for-testing)
- [Architecture / module overview](#architecture--module-overview)
- [Known limitations](#known-limitations)

## How it works

1. Generate Doxygen XML (and, optionally, HTML) output for both the **old**
   and the **new** version of your project, using **the same Doxygen
   version** and **the same Doxyfile settings** for both runs (only the
   `INPUT`/`OUTPUT_DIRECTORY` should differ) - see below for why this
   matters and which settings are required.
2. Run `doxydiff` pointing it at both XML output directories (and,
   optionally, both HTML output directories to also get graph diffs).
3. Open the generated `index.html` report.

`doxydiff` parses every compound (`class`, `struct`, `union`, `interface`,
`namespace`, `file`, `dir`, `page`, `group`, `concept`) and every member
(`function`, `variable`, `typedef`, `enum`, `define`, ...) from the XML,
computes a normalized, diffable text representation of every
brief/detailed description (this is also how markdown pages, which Doxygen
turns into a `page` compound, are covered automatically - no special
casing needed), and matches old vs. new elements **by qualified name and
signature**, not by their position in the XML or their internal Doxygen ID
(refid) - IDs are reasonably stable across unrelated changes but still
depend on scope+signature, so identity by name is the safer, more
transparent choice.

### Move detection

If a function/variable disappears from its old scope (class/namespace) and
an item with the same simple name and the same parameter *types* appears
unambiguously in exactly one different scope, it is reported as **moved**
instead of removed+added (this also works across files - e.g. moving a
function into a different header).

### Graph diff strategy (avoiding the "everything shifted" problem)

Doxygen (with `DOT_CLEANUP = NO`) leaves the raw Graphviz `.dot` sources for
every call graph, caller graph, inheritance/collaboration graph and include
graph next to the HTML output. Rendering the graph as an image and comparing
pixels would be wrong: adding a single new function call can reflow the
*entire* graph, making a naive pixel diff mark almost everything as
"changed".

Instead `doxydiff`:

1. Parses the `.dot` source and identifies each node by its Doxygen-assigned
   **label** (the readable, qualified function/class name) - never by its
   positional `NodeN` variable name, which is meaningless across versions.
2. Computes a pure, layout-independent **set diff** of node labels and
   edges (`(source label, target label)` pairs).
3. Renders the **new** graph itself via `dot -Tpng` / `dot -Tcmapx` to get
   pixel-accurate bounding boxes for every node in the new layout, then
   draws a red rectangle only around the nodes that are genuinely new -
   regardless of where the layout engine happened to place them.

### Image diff strategy

Images referenced via Markdown (`![...](...)`) or `\image` commands are
found while rendering descriptions and are compared with OpenCV: both
images are aligned on a common canvas, diffed, thresholded, and the
bounding box of the changed region(s) is drawn as a red rectangle on the new
image - the same "red box around what changed" idea used for graphs.

### Mermaid diagram diff strategy

Doxygen (since it added `\mermaid`/`\endmermaid` support, ~1.17+) does
**not** pre-render Mermaid diagrams like it does Graphviz graphs: the raw
Mermaid source text is stored verbatim in the XML and rendered *client-side*
in the browser by mermaid.js. There is no `.dot`-like intermediate file and
no server-side layout to reuse, so `doxydiff` renders the diagrams itself
via the [Mermaid CLI](https://github.com/mermaid-js/mermaid-cli) (`mmdc`,
which drives a headless Chromium through Puppeteer) - by default run
on-demand via `npx --yes @mermaid-js/mermaid-cli` so no global Node package
install is required, only Node.js itself.

- For **`flowchart`/`graph`** diagrams (structurally similar to the
  Graphviz call graphs), `doxydiff` parses the Mermaid source itself and
  extracts the node/edge sets - a pure, layout-independent structural diff,
  same idea as the `.dot` diff above. It then injects a Mermaid
  `classDef`/`class` styling directive for every *added* node directly into
  the **new** diagram's source before rendering, so Mermaid itself draws
  the new nodes in red - no bounding-box math needed at all, since Mermaid
  does the highlighting natively.
- For **every other diagram kind** (`sequenceDiagram`, `classDiagram`,
  `stateDiagram`, `erDiagram`, `pie`, `gantt`, `timeline`, `mindmap`, ...)
  there is no node/edge model to parse, so `doxydiff` falls back to
  rendering both the old and new diagram to PNG and reuses the same OpenCV
  pixel-diff/bounding-box technique as for plain images. This still
  reliably flags "this diagram changed" and shows *where*, but - like a
  naive Graphviz pixel diff - a layout reflow (e.g. one more sequence
  message shifting everything below it) can make the highlighted region
  larger than the conceptual change; only the flowchart path avoids this.

The diagram's raw Mermaid source is also always included as a normal
git-diff style text diff (added/removed lines) next to the rendered image,
regardless of diagram kind.

## Requirements

- Python 3.9+
- [Doxygen](https://www.doxygen.nl/) (tested with 1.9.8 and 1.18.0; use
  1.17+ for `\mermaid`/`\endmermaid` support) - **the same version** must
  be used for both the old and the new run, since Doxygen's XML/dot output
  format can change between versions and that would show up as noise in
  the diff.
- [Graphviz](https://graphviz.org/) (`dot` executable on `PATH`) - only
  needed if you want call-graph/inheritance-graph diffs. `doxydiff` also
  auto-detects `dot.exe` under the common Windows install locations
  (`C:\Program Files\Graphviz\bin`) even if it isn't on `PATH`; if that
  fails, add that folder to your `PATH` environment variable (or pass
  `--dot "C:\Program Files\Graphviz\bin\dot.exe"`).
- [Node.js](https://nodejs.org/) (with `npx` on `PATH`) - only needed if
  your documentation uses `\mermaid`/`\endmermaid` diagrams; used to run the
  [Mermaid CLI](https://github.com/mermaid-js/mermaid-cli) on demand
  (`npx --yes @mermaid-js/mermaid-cli`, no install required). Override with
  `--mmdc` if you have `mmdc` installed globally or need a custom Puppeteer
  config. `doxydiff` also auto-detects `npx`/`node` under the common
  Windows install locations (`C:\Program Files\nodejs`) even if they aren't
  on `PATH`; if resolution still fails (e.g. Node.js isn't installed at
  all), install it from nodejs.org (the installer adds it to `PATH`
  automatically) or add its install folder to `PATH` manually.
- Python packages: `opencv-python-headless`, `numpy`, `Pillow` (installed
  automatically, see [Installation](#installation)).

## Required Doxyfile settings

Both the old and the new Doxygen run **must** use the same `Doxyfile`
settings (only `INPUT` and `OUTPUT_DIRECTORY` may differ) - otherwise
differences in the generated XML would be caused by configuration drift
rather than by actual documentation changes. The following settings are
required or strongly recommended:

| Setting | Value | Why |
|---|---|---|
| `GENERATE_XML` | `YES` | doxydiff parses the XML output. |
| `XML_PROGRAMLISTING` | `YES` | keeps source excerpts in the XML (optional, but useful for future source-level diffing). |
| `CREATE_SUBDIRS` | `NO` | keeps XML/HTML file names predictable and flat, which the image/graph lookup in doxydiff relies on. |
| `SORT_MEMBER_DOCS` | `YES` | stable member order reduces order-based diff noise. |
| `SORT_BRIEF_DOCS` | `YES` | same reason. |
| `SORT_GROUP_NAMES` | `YES` | same reason. |
| `SORT_BY_SCOPE_NAME` | `YES` | same reason. |
| `MARKDOWN_SUPPORT` | `YES` | needed so `.md` pages are parsed into `page` compounds. |
| `USE_MDFILE_AS_MAINPAGE` | e.g. `docs/mainpage.md` | needed if you want your main markdown page diffed as the `indexpage` compound. |
| `HAVE_DOT` | `YES` | required for any graphs. |
| `CALL_GRAPH` | `YES` | generates call graphs (function → functions it calls). |
| `CALLER_GRAPH` | `YES` | generates caller graphs (function → functions that call it). |
| `DOT_CLEANUP` | `NO` | **critical**: keeps the `.dot` source files in the HTML output directory; without this, doxydiff cannot do a structural graph diff. |
| `SOURCE_BROWSER` | `YES` | required for Doxygen to actually compute call/caller relationships (`REFERENCED_BY_RELATION`/`REFERENCES_RELATION` below need this too). |
| `REFERENCED_BY_RELATION` | `YES` | without this (the default is `NO`!), Doxygen does not generate caller graphs at all. |
| `REFERENCES_RELATION` | `YES` | same reason, for call graphs. |
| `EXTRACT_ALL` | `YES` | ensures undocumented-but-changed entities still show up in the XML (recommended, optional). |
| `GENERATE_HTML` | `YES` | needed to get the `.dot`/`.map` graph sources on disk (only the HTML generator writes them). |
| `IMAGE_PATH` | your image folder(s) | so `\image` / markdown images are found and copied into the output. |

> **Important:** `REFERENCED_BY_RELATION` and `REFERENCES_RELATION` default
> to `NO` in a fresh Doxyfile. Without setting them to `YES` (together with
> `SOURCE_BROWSER = YES`), Doxygen silently generates **no call/caller
> graphs at all**, even with `HAVE_DOT`/`CALL_GRAPH`/`CALLER_GRAPH` all set
> to `YES` - this was discovered and fixed while building the demo project
> for this tool.

A ready-to-copy Doxyfile fragment can be found in
[`demo-project/v1/Doxyfile`](demo-project/v1/Doxyfile) and
[`demo-project/v2/Doxyfile`](demo-project/v2/Doxyfile) in this repository
(both are patched from a stock `doxygen -g` template with exactly the
settings above).

## Installation

Make sure the [Requirements](#requirements) (Python 3.9+, Doxygen and, for
the optional features, Graphviz and Node.js) are available first.

```powershell
cd doxydiff
python -m pip install -e .
```

(or simply `python -m pip install opencv-python-headless numpy Pillow` and
run the tool as `python -m doxydiff.cli ...` without installing it.)

### Using a virtual environment (optional)

A virtual environment is not required. It is recommended because it keeps
`opencv-python-headless`, `numpy` and `Pillow` out of your global Python
installation, avoiding version conflicts with other projects. On
Linux/macOS, distribution-managed Pythons often refuse a global `pip
install` altogether ([PEP 668](https://peps.python.org/pep-0668/)).

```powershell
cd doxydiff
python -m venv .venv
.venv\Scripts\Activate.ps1      # Linux/macOS: source .venv/bin/activate
python -m pip install -e .
```

## Usage

```powershell
doxydiff `
  --old-xml  path\to\old\doxygen-out\xml `
  --new-xml  path\to\new\doxygen-out\xml `
  --old-html path\to\old\doxygen-out\html `
  --new-html path\to\new\doxygen-out\html `
  --out      path\to\report `
  --name     "My Project" `
  --json-summary path\to\summary.json `
  --max-doc-lines-removed-pct 10
```

- `--old-xml` / `--new-xml` (required): the two Doxygen `XML_OUTPUT`
  directories to compare.
- `--old-html` / `--new-html` (optional): the two Doxygen HTML output
  directories; needed both for call-graph/inheritance-graph diffs *and* for
  the "view in v1/v2 docs" links described below (and only works if
  `DOT_CLEANUP = NO` was set when generating them).
- `--out` (required): directory the HTML report (`index.html` + `assets/`)
  is written to.
- `--dot`: path to the Graphviz `dot` executable if it's not on `PATH`.
- `--mmdc`: command used to render Mermaid diagrams; default
  `npx --yes @mermaid-js/mermaid-cli` (requires Node.js only, no install).
- `--json-summary PATH`: write the change statistics as JSON to `PATH` (see
  [CI / regression checks](#ci--regression-checks)).
- `--max-removed-members`, `--max-removed-compounds`,
  `--max-doc-lines-removed`, `--max-doc-lines-removed-pct`: optional CI
  thresholds; see below.

Open `report/index.html` in a browser. The top of the page shows summary
statistics and a table listing every difference; each row links to a
detailed, git-diff style view further down the page.

## Linking into the real Doxygen HTML output

When `--old-html`/`--new-html` are given, every detail section in the
report (compounds, members, images, and graphs) gets one or two small
"📂 view in v1 docs" / "📂 view in v2 docs" buttons that link directly into
Doxygen's own generated HTML — only the side(s) on which the element
actually exists get a button (e.g. a function that only exists in v2 only
gets a "view in v2 docs" link).

Example: if `include/TextUtils.h` (and its two call/caller graphs) were
added in v2, the report shows only a "view in v2 docs" link for the file
and for each of its graphs — since there is nothing to view in v1. For a
*member* (e.g. `Calculator::divide`) that exists in both versions, the
link points not just at the compound's page but at the exact anchor of
that member (`class_calculator.html#a...`), and the same precise anchor is
used for its call-graph/caller-graph ("cgraph"/"icgraph") links. Graphs
that belong to a whole file/class/namespace (include graphs, inheritance
graphs, ...) link to the top of that compound's page instead.

This works because Doxygen's HTML file/anchor naming is a documented,
stable convention (implemented in `doxydiff/doxylink.py`):
a compound's page is `{refid}.html` (the `indexpage` compound is the one
exception, mapping to `index.html`), and a member's anchor is the
hex-hash suffix of its memberdef `id` after the `_1` separator, e.g.
`class_calculator_1a7d50...` → anchor `a7d50...` on `class_calculator.html`.
No extra Doxyfile setting is required beyond what's already needed for the
XML/graph diff itself.

## CI / regression checks

Every report also records the change counts in a `Stats` object which is
exposed two ways:

1. **Exit code.** If any `--max-...` threshold is exceeded, `doxydiff`
   prints a `REGRESSION DETECTED:` block listing which threshold(s) failed
   and exits with code **1** (instead of 0). Argument errors (e.g. missing
   `--out`) use argparse's standard exit code **2**. This means a CI step
   can simply check the process exit code:

   ```powershell
   doxydiff --old-xml v1\xml --new-xml v2\xml --out report `
     --max-doc-lines-removed-pct 10 --max-removed-members 0
   if ($LASTEXITCODE -ne 0) { Write-Error "Documentation regression detected"; exit 1 }
   ```

   Available thresholds:
   - `--max-removed-members N` — fail if more than `N` members were removed.
   - `--max-removed-compounds N` — fail if more than `N` compounds
     (classes/namespaces/files/...) were removed.
   - `--max-doc-lines-removed N` — fail if more than `N` documentation
     lines were removed.
   - `--max-doc-lines-removed-pct X` — fail if more than `X`% of the *old*
     version's total documentation lines were removed. This is the most
     useful one for catching "a lot of documentation just disappeared",
     since it's normalized against project size instead of an absolute count.
   - If no threshold flag is given, the exit code is always 0 (report-only
     mode); thresholds are purely opt-in.

2. **JSON summary.** `--json-summary path\to\summary.json` writes all
   `Stats` fields (`compounds_added/removed/modified`,
   `members_added/removed/modified/moved`, `images_changed`,
   `graphs_changed`, `mermaid_changed`, `lines_added/removed`,
   `doc_lines_old_total`, `lines_removed_pct`) as JSON, so a pipeline can
   archive it as a build artifact, chart it over time, or apply more
   elaborate custom logic than the built-in thresholds.

The same summary line is also always printed to stdout, e.g.:

```
Summary: compounds +3/-0/~3, members +2/-1/~2/moved:1, images changed: 1, graphs changed: 10, mermaid diagrams changed: 2, doc lines +5/-4 (8.0% of old total removed)
```

## Demo project used for testing

Since no existing tool (`diff-html`, `DoxygenCompare`, ...) covers this use
case, a small, self-contained C++ demo project with two deliberately
different versions was created under [`demo-project/`](demo-project) to
exercise every kind of change doxydiff needs to detect:

| Change | v1 → v2 |
|---|---|
| modified function doc | `Calculator::add` description expanded |
| removed function | `Calculator::multiply` removed |
| added function | `Calculator::divide` added |
| moved function (cross-namespace) | `StringUtils::trim` → `TextUtils::trim` (new header/namespace) |
| added function (new call graph node) | `logResult()` added, called from `main()` |
| changed markdown page | `docs/mainpage.md` text changed |
| changed image | `images/logo.png` gets an added red badge |
| shifted call graph | `main()`'s call graph gains/loses nodes, reordering the whole layout |
| changed Mermaid flowchart | `Calculator`'s `\mermaid` control-flow diagram gains an `Overflow?` decision node |
| changed Mermaid sequence diagram | `StringUtils`'s `\mermaid` usage-sequence diagram gains a `trim()` call |

The Doxygen output of the demo project is **not** part of the repository and
has to be built first (tested with Doxygen 1.18.0, see
[Requirements](#requirements); the settings are in `demo-project/v1/Doxyfile`
and `demo-project/v2/Doxyfile`). Follow the steps from
[Installation](#installation) and run the following from the repository root:

```powershell
# 1. Build the Doxygen output (XML + HTML) for both versions
cd demo-project\v1; doxygen Doxyfile; cd ..\..
cd demo-project\v2; doxygen Doxyfile; cd ..\..

# 2. Compare them
doxydiff `
  --old-xml  demo-project\v1\doxygen-out\xml `
  --new-xml  demo-project\v2\doxygen-out\xml `
  --old-html demo-project\v1\doxygen-out\html `
  --new-html demo-project\v2\doxygen-out\html `
  --out      report `
  --name     "Demo"

# 3. View the result
start report\index.html
```

(`doxygen` must be on your `PATH`, otherwise call it by its full path.)
The generated report was verified (including
via a headless-browser screenshot) to correctly show:

- the `add`/`multiply`/`divide` changes as modified/removed/added
- `StringUtils::trim` → `TextUtils::trim` as **moved**, not delete+add
- the markdown page diff with red/green highlighted paragraphs
- `logo.png` with only the new red badge outlined in red
- the `main()` call graph with **only** `divide`, `logResult` and
  `TextUtils::trim` outlined in red, even though the whole graph reflowed
- the `Calculator` Mermaid flowchart re-rendered with **only** the new
  `Overflow?` node outlined in red
- the `StringUtils` Mermaid sequence diagram rendered as a generic
  before/after pixel diff (no structural node model for this diagram kind)

## Architecture / module overview

```
doxydiff/
  model.py       data classes: Compound, Member, Project
  render.py      renders Doxygen description XML to normalized diffable text
  xmlparse.py    parses a Doxygen XML output directory into a Project
  matcher.py     matches old vs. new Project by qualified identity;
                 detects added/removed/modified/moved
  textdiff.py    git-diff style word-level and line-level HTML diff (difflib)
  imagediff.py   OpenCV pixel diff + red bounding box for embedded images
  graphdiff.py   structural .dot diff + red bounding box for graph nodes
  mermaiddiff.py Mermaid diagram parsing/rendering: structural flowchart
                 diff + red node highlighting, generic pixel diff fallback
                 for other diagram kinds
  report.py      assembles the overview + detail HTML report
  cli.py         command line entry point
```

## Known limitations

- Free functions/variables at file scope are matched globally by
  `name(argument types)`; two unrelated global functions with an identical
  name and signature in different files would be treated as "the same"
  element. Namespace/class members are unaffected (they are always matched
  within their qualified scope).
- Move detection only reclassifies a removed+added pair as "moved" when the
  pairing is unambiguous (exactly one candidate on each side); ambiguous
  cases fall back to separate add/remove entries.
- Whole-compound renames (e.g. renaming class `Foo` to `Bar` with no other
  changes) are currently reported as one compound removed + one compound
  added, not as a "renamed" compound - only *members* moving between
  compounds are detected as moves.
- Image discovery is currently based on `\image`/markdown image references
  found while rendering descriptions (looked up by file name directly in
  the XML output directory, where Doxygen also copies referenced images) -
  images embedded through other custom mechanisms are not picked up.
- The Mermaid `flowchart`/`graph` parser only supports the common subset of
  Mermaid's grammar (standard node shapes and arrow styles, `|label|` and
  inline `-- label -->` edge labels); anything it cannot make sense of is
  silently skipped rather than raising, so an unusual/unsupported statement
  simply won't show up in the structural node/edge diff (though it is
  always still visible in the plain text diff of the raw source). All other
  Mermaid diagram kinds (sequence, class, state, ER, pie, gantt, timeline,
  mindmap, ...) are not structurally parsed at all and only get the generic
  rendered-pixel diff described above.
- Mermaid diagrams are matched across old/new by their position (index)
  within the same compound's/member's description, not by any Mermaid-level
  identity; inserting a new diagram before an existing one in the same
  description will shift this pairing.

## Roadmap / possible future work

Linking into the real Doxygen HTML output and CI-friendly exit codes /
JSON summaries (described above) are already implemented. Ideas for further
work:

- Detect whole-compound renames (not just member moves) as "renamed"
  instead of remove+add.
- Disambiguate same-named/same-signature global functions by file.
- Optional true side-by-side rendered-HTML diff (vs. today's XML-derived
  report plus links into the HTML) for cases where custom Doxygen HTML
  templates/CSS themselves need to be compared.
