# Demo Project {#mainpage}

This is a small demo project used to test **doxydiff**, a tool that compares
Doxygen documentation between two versions of a software project.

## Features

- A simple `Calculator` class with basic arithmetic operations (now including
  division instead of multiplication).
- String utility functions in the `StringUtils` namespace.
- Text utility functions in the new `TextUtils` namespace (split off from
  `StringUtils` in this version).

## Architecture

![Logo](images/logo.png)

The application now also logs intermediate results via a small `logResult`
helper function, which adds an additional call in the generated call graphs.
