# Vapourtec R-Series Example Scripts (Not Included)

The Vapourtec R-Series Python API (`rseriesopc`) and its example scripts are distributed by Vapourtec Ltd and are not redistributed in this repository.

LabAutoMate can use these scripts as reference context when generating Dash applications that control a Vapourtec R-Series system (Tab 2, **Include Vapourtec SDK examples**). To enable this option:

1. Obtain the R-Series Python API and its example scripts from [Vapourtec Ltd](https://www.vapourtec.com).
2. Copy the example `.py` files into this folder.
3. Restart LabAutoMate. The checkbox shows how many files were found.

LabAutoMate loads every `.py` file in this folder, so the file names do not need to match exactly. The study used the following 11 example scripts:

| # | File | Content |
|---|------|---------|
| 1 | `Vapourtec_Example1.py` | Manual control demonstration via OPC UA |
| 2 | `Vapourtec_Example2.py` | Manual control of R2 primary/secondary pumps and valves |
| 3 | `Vapourtec_manualControlExample.py` | Example 1: Manual control (flow-rate ramp at constant temperature) |
| 4 | `Vapourtec_readingDataExample.py` | Example 2: Reading data from sensors (subscription and polling) |
| 5 | `Vapourtec_reactionParametersExample.py` | Example 3: Reaction parameters |
| 6 | `Vapourtec_addingReactionExample.py` | Example 4a: Adding a reaction |
| 7 | `Vapourtec_modifyingReactionExample.py` | Example 4b: Modifying a reaction |
| 8 | `Vapourtec_makingReactionsExample.py` | Example 5: Making a series of reactions |
| 9 | `Vapourtec_getAndLoadExperimentsExample.py` | Example 6: Getting and loading experiments |
| 10 | `Vapourtec_importCsvExample.py` | Example 7: Importing a reaction CSV |
| 11 | `Vapourtec_reactionManagerDemo.py` | Reaction Manager walk-through |

Generated applications that control a Vapourtec system also need the `rseriesopc` package installed from Vapourtec.
