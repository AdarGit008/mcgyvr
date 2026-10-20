"""Go symbol extraction, held to real source rather than to examples written for it.

Every excerpt below is copied verbatim from an MIT-licensed Go repository, at the
commit and lines its comment names, and is only parsed here, never built or run.
Between them they hold what a Go extractor has to get right: generic types and
functions, dot, blank and aliased imports, the capitalisation rule that decides what
a package exports, const and var blocks, and a file that stops mid-declaration.
"""

from __future__ import annotations

from mcgyvr.orchestrator.symbols import Symbol, SymbolKind, extract, language_of


def _of(kind: SymbolKind, source: bytes) -> list[Symbol]:
    return [s for s in extract("pkg/file.go", source) if s.kind is kind]


def _definitions(source: bytes) -> set[tuple[str, int, str, str]]:
    return {
        (s.name, s.line, s.detail, s.signature)
        for s in _of(SymbolKind.DEFINITION, source)
    }


def _exports(source: bytes) -> set[tuple[str, int]]:
    return {(s.name, s.line) for s in _of(SymbolKind.EXPORT, source)}


def _imports(source: bytes) -> list[tuple[str, int, str]]:
    return sorted((s.name, s.line, s.detail) for s in _of(SymbolKind.IMPORT, source))


def _references(source: bytes) -> set[tuple[str, int]]:
    return {(s.name, s.line) for s in _of(SymbolKind.REFERENCE, source)}


# Generic struct types and a method on a generic receiver.
# Source: https://github.com/samber/lo
#   commit 5c6ddcb7063c9908031340db03f27ba7483d1ece
#   types.go lines 1-19
#   MIT License, Copyright (c) 2022-2025 Samuel Berthe
TYPES = rb"""package lo

// Entry defines a key/value pairs.
type Entry[K comparable, V any] struct {
	Key   K
	Value V
}

// Tuple2 is a group of 2 elements (pair).
type Tuple2[A, B any] struct {
	A A
	B B
}

// Unpack returns values contained in a tuple.
// Play: https://go.dev/play/p/yrtn7QJTmL_E
func (t Tuple2[A, B]) Unpack() (A, B) {
	return t.A, t.B
}
"""


# A versioned standard-library import path (`math/rand/v2`).
# Source: https://github.com/samber/lo
#   commit 5c6ddcb7063c9908031340db03f27ba7483d1ece
#   benchmark/it_helpers_test.go lines 1-21
#   MIT License, Copyright (c) 2022-2025 Samuel Berthe
HELPERS = rb"""//go:build go1.23

package benchmark

import (
	"iter"
	"math/rand/v2"
	"strconv"
)

var itLengths = []int{10, 100, 1000}

func genStrings(n int) iter.Seq[string] {
	return func(yield func(string) bool) {
		for range n {
			if !yield(strconv.Itoa(rand.IntN(100_000))) {
				break
			}
		}
	}
}
"""


# A generic function with an unexported name.
# Source: https://github.com/onsi/ginkgo
#   commit 7ff96d7d0173ba4e059708f55910c1cb298c9818
#   internal/reporters/gojson.go lines 1-15
#   MIT License, Copyright (c) 2013-2014 Onsi Fakhouri
GOJSON = rb"""package reporters

import (
	"errors"
	"fmt"
	"strings"
	"time"

	"github.com/onsi/ginkgo/v2/types"
	"golang.org/x/tools/go/packages"
)

func ptr[T any](in T) *T {
	return &in
}
"""


# Dot imports, and package-level vars that export nothing.
# Source: https://github.com/onsi/ginkgo
#   commit 7ff96d7d0173ba4e059708f55910c1cb298c9818
#   ginkgo/ginkgo_cli_suite_test.go lines 1-22
#   MIT License, Copyright (c) 2013-2014 Onsi Fakhouri
SUITE = r"""package main

import (
	"testing"

	"github.com/onsi/ginkgo/v2/internal/test_helpers"

	. "github.com/onsi/ginkgo/v2"
	. "github.com/onsi/gomega"
)

func TestGinkgoCLI(t *testing.T) {
	RegisterFailHandler(Fail)
	RunSpecs(t, "Ginkgo CLI Suite")
}

var anchors test_helpers.Anchors
var _ = BeforeSuite(func() {
	var err error
	anchors, err = test_helpers.LoadAnchors(test_helpers.DOCS, "../")
	Ω(err).ShouldNot(HaveOccurred())
})
""".encode()


# A blank import, under build constraints.
# Source: https://github.com/onsi/ginkgo
#   commit 7ff96d7d0173ba4e059708f55910c1cb298c9818
#   ginkgo_cli_dependencies.go lines 1-8
#   MIT License, Copyright (c) 2013-2014 Onsi Fakhouri
DEPENDENCIES = rb"""//go:build ginkgoclidependencies
// +build ginkgoclidependencies

package ginkgo

import (
	_ "github.com/onsi/ginkgo/v2/ginkgo"
)
"""


# An aliased import among plain ones.
# Source: https://github.com/onsi/ginkgo
#   commit 7ff96d7d0173ba4e059708f55910c1cb298c9818
#   ginkgo/generators/bootstrap_command.go lines 1-14
#   MIT License, Copyright (c) 2013-2014 Onsi Fakhouri
BOOTSTRAP = rb"""package generators

import (
	"bytes"
	"encoding/json"
	"fmt"
	"os"
	"text/template"

	sprig "github.com/go-task/slim-sprig/v3"
	"github.com/onsi/ginkgo/v2/ginkgo/command"
	"github.com/onsi/ginkgo/v2/ginkgo/internal"
	"github.com/onsi/ginkgo/v2/types"
)
"""


# Types, a const block, an interface, a struct, a function and methods.
# Source: https://github.com/onsi/ginkgo
#   commit 7ff96d7d0173ba4e059708f55910c1cb298c9818
#   internal/writer.go lines 1-64
#   MIT License, Copyright (c) 2013-2014 Onsi Fakhouri
WRITER = rb"""package internal

import (
	"bytes"
	"fmt"
	"io"
	"sync"

	"github.com/go-logr/logr"
	"github.com/go-logr/logr/funcr"
)

type WriterMode uint

const (
	WriterModeStreamAndBuffer WriterMode = iota
	WriterModeBufferOnly
)

type WriterInterface interface {
	io.Writer

	Truncate()
	Bytes() []byte
	Len() int
}

// Writer implements WriterInterface and GinkgoWriterInterface
type Writer struct {
	buffer    *bytes.Buffer
	outWriter io.Writer
	lock      *sync.Mutex
	mode      WriterMode

	streamIndent []byte
	indentNext   bool

	teeWriters []io.Writer
}

func NewWriter(outWriter io.Writer) *Writer {
	return &Writer{
		buffer:       &bytes.Buffer{},
		lock:         &sync.Mutex{},
		outWriter:    outWriter,
		mode:         WriterModeStreamAndBuffer,
		streamIndent: []byte("  "),
		indentNext:   true,
	}
}

func (w *Writer) SetMode(mode WriterMode) {
	w.lock.Lock()
	defer w.lock.Unlock()
	w.mode = mode
}

func (w *Writer) Len() int {
	w.lock.Lock()
	defer w.lock.Unlock()
	return w.buffer.Len()
}

var newline = []byte("\n")
"""


# Type aliases and a package-level var block.
# Source: https://github.com/onsi/ginkgo
#   commit 7ff96d7d0173ba4e059708f55910c1cb298c9818
#   types/deprecated_types.go lines 1-31
#   MIT License, Copyright (c) 2013-2014 Onsi Fakhouri
DEPRECATED = rb"""package types

import (
	"strconv"
	"time"
)

/*
	A set of deprecations to make the transition from v1 to v2 easier for users who have written custom reporters.
*/

type SuiteSummary = DeprecatedSuiteSummary
type SetupSummary = DeprecatedSetupSummary
type SpecSummary = DeprecatedSpecSummary
type SpecMeasurement = DeprecatedSpecMeasurement
type SpecComponentType = NodeType
type SpecFailure = DeprecatedSpecFailure

var (
	SpecComponentTypeInvalid                 = NodeTypeInvalid
	SpecComponentTypeContainer               = NodeTypeContainer
	SpecComponentTypeIt                      = NodeTypeIt
	SpecComponentTypeBeforeEach              = NodeTypeBeforeEach
	SpecComponentTypeJustBeforeEach          = NodeTypeJustBeforeEach
	SpecComponentTypeAfterEach               = NodeTypeAfterEach
	SpecComponentTypeJustAfterEach           = NodeTypeJustAfterEach
	SpecComponentTypeBeforeSuite             = NodeTypeBeforeSuite
	SpecComponentTypeSynchronizedBeforeSuite = NodeTypeSynchronizedBeforeSuite
	SpecComponentTypeAfterSuite              = NodeTypeAfterSuite
	SpecComponentTypeSynchronizedAfterSuite  = NodeTypeSynchronizedAfterSuite
)
"""  # noqa: E501


# Cut mid-way through a const block, so the file does not parse.
# Source: https://github.com/onsi/ginkgo
#   commit 7ff96d7d0173ba4e059708f55910c1cb298c9818
#   types/label_filter.go lines 125-140
#   MIT License, Copyright (c) 2013-2014 Onsi Fakhouri
LABEL_FILTER = rb"""type lfToken uint

const (
	lfTokenInvalid lfToken = iota

	lfTokenRoot
	lfTokenOpenGroup
	lfTokenCloseGroup
	lfTokenNot
	lfTokenAnd
	lfTokenOr
	lfTokenRegexp
	lfTokenLabel
	lfTokenSetKey
	lfTokenSetOperation
	lfTokenSetArgument
"""


# An unaliased import of a package named `v1`, used as `v1.` on line 20.
# Source: https://github.com/wagoodman/dive
#   commit d6c691947f8fda635c952a17ee3b7555379d58f0
#   cmd/dive/cli/internal/options/ui_diff.go lines 1-24
#   MIT License, Copyright (c) 2018 Alex Goodman
UI_DIFF = rb"""package options

import (
	"github.com/anchore/clio"
	"github.com/wagoodman/dive/cmd/dive/cli/internal/ui/v1"
	"github.com/wagoodman/dive/internal/log"
)

var _ interface {
	clio.PostLoader
	clio.FieldDescriber
} = (*UIDiff)(nil)

// UIDiff provides configuration for how differences are displayed
type UIDiff struct {
	Hide []string `yaml:"hide" mapstructure:"hide"`
}

func DefaultUIDiff() UIDiff {
	prefs := v1.DefaultPreferences()
	return UIDiff{
		Hide: prefs.FiletreeDiffHide,
	}
}
"""


def test_a_go_file_is_go() -> None:
    assert language_of("internal/writer.go") == "go"
    assert language_of("internal/writer_test.go") == "go"


def test_generic_types_and_a_generic_receiver_method_are_definitions() -> None:
    assert _definitions(TYPES) == {
        ("Entry", 4, "struct", "type Entry[K comparable, V any] struct"),
        ("Tuple2", 10, "struct", "type Tuple2[A, B any] struct"),
        ("Unpack", 17, "method", "func (t Tuple2[A, B]) Unpack() (A, B)"),
    }


def test_capitalised_types_fields_and_methods_are_exported() -> None:
    assert _exports(TYPES) == {
        ("Entry", 4),
        ("Key", 5),
        ("Value", 6),
        ("Tuple2", 10),
        ("A", 11),
        ("B", 12),
        ("Unpack", 17),
    }


def test_a_generic_function_with_a_lowercase_name_is_defined_but_not_exported() -> None:
    assert _definitions(GOJSON) == {
        ("ptr", 13, "function", "func ptr[T any](in T) *T"),
    }
    assert _exports(GOJSON) == set()


def test_an_import_is_named_by_the_last_element_of_its_path() -> None:
    assert _imports(GOJSON) == [
        ("errors", 4, "errors"),
        ("fmt", 5, "fmt"),
        ("packages", 10, "golang.org/x/tools/go/packages"),
        ("strings", 6, "strings"),
        ("time", 7, "time"),
        ("types", 9, "github.com/onsi/ginkgo/v2/types"),
    ]


def test_a_major_version_element_does_not_name_the_import() -> None:
    assert ("rand", 7, "math/rand/v2") in _imports(HELPERS)


def test_an_aliased_import_is_named_by_its_alias() -> None:
    imports = _imports(BOOTSTRAP)
    assert ("sprig", 10, "github.com/go-task/slim-sprig/v3") in imports
    assert ("json", 5, "encoding/json") in imports
    statement = {s.signature for s in _of(SymbolKind.IMPORT, BOOTSTRAP) if s.line == 10}
    assert statement == {'import sprig "github.com/go-task/slim-sprig/v3"'}


def test_a_dot_import_is_a_star_import() -> None:
    imports = _imports(SUITE)
    assert ("*", 8, "github.com/onsi/ginkgo/v2") in imports
    assert ("*", 9, "github.com/onsi/gomega") in imports
    assert ("test_helpers", 6, "github.com/onsi/ginkgo/v2/internal/test_helpers") in (
        imports
    )


def test_a_blank_import_is_named_after_the_path_it_imports_for_effect() -> None:
    assert _imports(DEPENDENCIES) == [
        (
            "github.com/onsi/ginkgo/v2/ginkgo",
            7,
            "github.com/onsi/ginkgo/v2/ginkgo",
        )
    ]
    assert _of(SymbolKind.DEFINITION, DEPENDENCIES) == []


def test_package_level_vars_named_lowercase_or_blank_export_nothing() -> None:
    assert _exports(SUITE) == {("TestGinkgoCLI", 12)}
    assert {name for name, *_ in _definitions(SUITE)} == {"TestGinkgoCLI"}


def test_calls_are_references_by_callee_or_selected_field() -> None:
    assert _references(SUITE) == {
        ("RegisterFailHandler", 13),
        ("RunSpecs", 14),
        ("BeforeSuite", 18),
        ("LoadAnchors", 20),
        ("Ω", 21),
        ("ShouldNot", 21),
        ("HaveOccurred", 21),
    }
    assert {("Itoa", 16), ("IntN", 16), ("yield", 16)} <= _references(HELPERS)


def test_types_interfaces_functions_and_methods_of_one_file() -> None:
    assert _definitions(WRITER) == {
        ("WriterMode", 13, "type", "type WriterMode uint"),
        ("WriterInterface", 20, "interface", "type WriterInterface interface"),
        ("Truncate", 23, "method", "Truncate()"),
        ("Bytes", 24, "method", "Bytes() []byte"),
        ("Len", 25, "method", "Len() int"),
        ("Writer", 29, "struct", "type Writer struct"),
        ("NewWriter", 41, "function", "func NewWriter(outWriter io.Writer) *Writer"),
        ("SetMode", 52, "method", "func (w *Writer) SetMode(mode WriterMode)"),
        ("Len", 58, "method", "func (w *Writer) Len() int"),
    }


def test_consts_are_exported_but_never_defined_and_lowercase_fields_are_neither() -> (
    None
):
    exports = _exports(WRITER)
    assert {("WriterModeStreamAndBuffer", 16), ("WriterModeBufferOnly", 17)} <= exports
    names = {name for name, _ in exports}
    assert names.isdisjoint({"buffer", "outWriter", "lock", "mode", "newline"})
    defined = {name for name, *_ in _definitions(WRITER)}
    assert defined.isdisjoint({"WriterModeStreamAndBuffer", "WriterModeBufferOnly"})


def test_type_aliases_are_definitions_and_a_var_block_exports_each_name() -> None:
    definitions = _definitions(DEPRECATED)
    assert (
        "SuiteSummary",
        12,
        "type",
        "type SuiteSummary = DeprecatedSuiteSummary",
    ) in (definitions)
    assert len(definitions) == 6
    exports = _exports(DEPRECATED)
    assert ("SpecComponentTypeInvalid", 20) in exports
    assert ("SpecComponentTypeSynchronizedAfterSuite", 30) in exports
    assert len(exports) == 6 + 11


def test_a_file_that_stops_mid_declaration_yields_what_parsed() -> None:
    """tree-sitter does not refuse a broken file: the type before the unterminated
    const block is still found, and the block's lowercase names export nothing."""
    assert _definitions(LABEL_FILTER) == {("lfToken", 1, "type", "type lfToken uint")}
    assert _exports(LABEL_FILTER) == set()


def test_a_v1_element_is_the_package_name_not_a_major_version() -> None:
    """Module major versions start at `/v2`; the file calls `v1.DefaultPreferences`."""
    assert (
        "v1",
        5,
        "github.com/wagoodman/dive/cmd/dive/cli/internal/ui/v1",
    ) in _imports(UI_DIFF)
