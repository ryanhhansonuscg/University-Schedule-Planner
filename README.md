# University Schedule Planner

Use the **University Schedule Planner Launcher** to collect, import, and explore
university schedule data.

1. Open the extracted project folder, then double-click `launch-planner.bat` on
   Windows or `launch-planner.command` on macOS.
   If Windows blocks the batch file, first confirm that you downloaded the
   official release and verified its published checksum. Then right-click
   `launch-planner.bat`, select **Properties**, select **Unblock** on the
   **General** tab, and choose **Apply**. If Microsoft Defender SmartScreen
   appears when you open it, select **More info**, verify that the displayed
   file is `launch-planner.bat`, and select **Run anyway**.
2. Start a conversation with a browsing-capable LLM and enter only the university
   name or one official university URL.
3. Attach the complete [LLM scraping guide](template/university-template/LLM-SCRAPING-GUIDE.md)
   in that conversation. The guide is the authoritative source for collection,
   safety, validation, and output requirements; do not replace it with directions
   copied from this README.
4. Review the LLM's validation report, especially every inaccessible page and
   ambiguity. Resolve any concern before accepting the result.
5. In the **University Schedule Planner Launcher**, choose **Import University ZIP…** for the returned ZIP, or
   choose the folder import option for one completed university folder. After the
   import succeeds, select **Open Planner**.

## Review scraped department data

Open **Data editor** from either browser page (or open `editor.html` directly),
then choose a scraped `departments/<CODE>.json` file. The editor keeps data local,
lets a reviewer correct course metadata and structured requirements, reports
structural problems, and downloads a corrected JSON copy. Run
`python tools/validate_university.py <university-folder>` on the complete folder
before importing or publishing it.

Requirement timing is explicit: a `prerequisite` must be completed in an earlier
term; a `corequisite` may be completed earlier or placed in the same term; and a
`recommended` relationship is advisory. Requirements sharing a `logic_group` use
`OR` when any one member is sufficient and `AND` when every member is required.
Un-grouped requirements are independently required. Preserve the catalog's prose
fields alongside these structured edges so ambiguous rules remain visible for
human confirmation.

## Import performance and acceleration

The **University Schedule Planner Launcher** keeps server health checks and import/build work off the Tk event
thread, reports department-reading and commit progress, and lets an in-progress
import be cancelled. Department JSON files may be decoded with bounded worker
concurrency; the conservative default is the smaller of four and the available
CPU count. **Python Settings** allows a specific worker count, and `0` disables
concurrency for diagnostics. Cross-file validation is aggregated in deterministic
filename order, after which `catalog.json`, the SQLite database, and the standalone
destination are committed in a controlled, single-threaded phase. Workers never
share a SQLite connection or write concurrently to the destination tree.

GPU acceleration is currently **unavailable and not beneficial** for this
JSON/SQLite workload. No GPU framework is required or imported. Run
`python tools/build_university.py --acceleration-report` for the machine-readable
capability report. A GPU backend should only be added for a measured future
workload with an optional implementation, deterministic CPU fallback, cancellation
semantics, and benchmarks showing that initialization and transfer costs are
recovered; GPU availability alone is not evidence that imports will be faster.

## Clean-machine release checklist

1. Download the versioned release ZIP and verify its published SHA-256 checksum.
2. Extract the ZIP into a new folder; do not run it from inside the ZIP viewer.
3. Confirm the active environment in Anaconda or Miniconda uses Python 3.10 or
   newer and includes tkinter, then double-click the platform bootstrap. The
   Windows bootstrap checks the active environment first, then `CONDA_EXE`, every
   `conda` result on `PATH`, and finally offers a file picker. If the selected
   base environment lacks a requirement, the error identifies that environment
   and prints the exact `conda install -n base ...` command to run.
   To check tkinter yourself, run `python -c "import tkinter; print(tkinter.TkVersion)"`
   in either Command Prompt or PowerShell. Run `conda list tk` to inspect the
   installed package. A prompt beginning with `(base) C:\>` is Command Prompt,
   where PowerShell's leading `&` invocation operator is not valid.
4. Import both a university ZIP and, when needed, its extracted university folder.
   The command-line importer remains available as an automation and accessibility
   fallback: `python tools/launcher.py --import-archive SOURCE [--replace]`.
5. Select **Open Planner**, wait for the managed local server to become ready, and
   confirm the planner opens. Close the **University Schedule Planner Launcher**
   and confirm its managed server process exits.

## Release contents and verification

University Schedule Planner releases include the **University Schedule Planner
Launcher**, reusable import service, managed loopback server, Windows and macOS
bootstrap scripts, and all non-generated planner UI resources. Release QA verifies
the exact allowlisted manifest and safe extraction, imports from both ZIP and
folder sources in an isolated extracted copy, checks generated registry and site
artifacts, and exercises server readiness, health, and shutdown.
