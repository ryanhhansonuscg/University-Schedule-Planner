# University Schedule Planner

Use the launcher to collect, import, and explore university schedule data.

1. Open the extracted project folder, then double-click `launch-planner.bat` on
   Windows or `launch-planner.command` on macOS.
2. Start a conversation with a browsing-capable LLM and enter only the university
   name or one official university URL.
3. Attach the complete [LLM scraping guide](template/university-template/LLM-SCRAPING-GUIDE.md)
   in that conversation. The guide is the authoritative source for collection,
   safety, validation, and output requirements; do not replace it with directions
   copied from this README.
4. Review the LLM's validation report, especially every inaccessible page and
   ambiguity. Resolve any concern before accepting the result.
5. In the launcher, choose **Import University ZIP…** for the returned ZIP, or
   choose the folder import option for one completed university folder. After the
   import succeeds, select **Open Planner**.

## Import performance and acceleration

The launcher keeps server health checks and import/build work off the Tk event
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
