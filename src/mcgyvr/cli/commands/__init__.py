# Package marker for the CLI command implementations. Holds no code of its own: the
# submodules (delegate, fleet, inspect, ladder, machine, repo, run, sandbox, setup,
# use) each build one command's parser and handler, and mcgyvr.cli.dispatcher
# imports them to assemble and run the command line.
