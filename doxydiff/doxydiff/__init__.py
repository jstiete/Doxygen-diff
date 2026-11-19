"""doxydiff - compare Doxygen documentation between two versions of a project.

The tool compares the Doxygen XML output of two source trees ("old" and
"new"), matches documented elements (classes, namespaces, files, functions,
variables, pages, groups, images and call/inheritance graphs) by their
qualified identity rather than by XML position, and produces a git-diff
style HTML report with an overview and per-element detail diffs.
"""

__version__ = "0.1.0"
