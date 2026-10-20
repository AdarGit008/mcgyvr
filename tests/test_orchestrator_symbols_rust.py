"""Rust symbol extraction, held to real source rather than to examples written for it.

Every excerpt below is copied verbatim from an MIT-licensed Rust repository, at the
commit and lines its comment names, and is only parsed here, never built or run.
Between them they hold what a Rust extractor has to get right: exactly `pub` is an
export and `pub(crate)` is not, `pub use` and `pub extern crate` re-export under
their aliases, `use` trees flatten to one import per name, methods are told from
functions, a `#[cfg(test)]` module and its `#[test]` functions contribute nothing,
macro bodies stay opaque, and a file cut mid-item still yields what parsed.
"""

from __future__ import annotations

from mcgyvr.orchestrator.symbols import Symbol, SymbolKind, extract, language_of


def _of(kind: SymbolKind, source: bytes) -> list[Symbol]:
    return [s for s in extract("src/file.rs", source) if s.kind is kind]


def _definitions(source: bytes) -> set[tuple[str, int, str, str]]:
    return {
        (s.name, s.line, s.detail, s.signature)
        for s in _of(SymbolKind.DEFINITION, source)
    }


def _exports(source: bytes) -> set[tuple[str, int]]:
    return {(s.name, s.line) for s in _of(SymbolKind.EXPORT, source)}


def _imports(source: bytes) -> set[tuple[str, int, str]]:
    return {(s.name, s.line, s.detail) for s in _of(SymbolKind.IMPORT, source)}


def _references(source: bytes) -> set[tuple[str, int]]:
    return {(s.name, s.line) for s in _of(SymbolKind.REFERENCE, source)}


# A nested use list, a `pub use` with an alias, and a trait impl's methods.
# Source: https://github.com/tokio-rs/tracing
#   commit 9d0e557728ecb91e467fc29dfe738b9f28cf6684
#   tracing-subscriber/src/filter/level.rs lines 1-27 (the whole file)
#   MIT License, Copyright (c) 2019 Tokio Contributors
LEVEL = rb"""use tracing_core::{
    subscriber::{Interest, Subscriber},
    Metadata,
};

#[allow(unreachable_pub)] // https://github.com/rust-lang/rust/issues/57411
pub use tracing_core::metadata::{LevelFilter, ParseLevelFilterError as ParseError};

// === impl LevelFilter ===

impl<S: Subscriber> crate::Layer<S> for LevelFilter {
    fn register_callsite(&self, metadata: &'static Metadata<'static>) -> Interest {
        if self >= metadata.level() {
            Interest::always()
        } else {
            Interest::never()
        }
    }

    fn enabled(&self, metadata: &Metadata<'_>, _: crate::layer::Context<'_, S>) -> bool {
        self >= metadata.level()
    }

    fn max_level_hint(&self) -> Option<LevelFilter> {
        Some(*self)
    }
}
"""  # noqa: E501


# Plain `use` declarations and a `pub const`.
# Source: https://github.com/tokio-rs/tracing
#   commit 9d0e557728ecb91e467fc29dfe738b9f28cf6684
#   tracing-appender/src/non_blocking.rs lines 47-67
#   MIT License, Copyright (c) 2019 Tokio Contributors
NON_BLOCKING = rb"""use crate::worker::Worker;
use crate::Msg;
use crossbeam_channel::{bounded, SendTimeoutError, Sender};
use std::io;
use std::io::Write;
use std::sync::atomic::AtomicUsize;
use std::sync::atomic::Ordering;
use std::sync::Arc;
use std::thread::JoinHandle;
use std::time::Duration;
use tracing_subscriber::fmt::MakeWriter;

/// The default maximum number of buffered log lines.
///
/// If [`NonBlocking`] is lossy, it will drop spans/events at capacity.
/// If [`NonBlocking`] is _not_ lossy, backpressure will be exerted on
/// senders, causing them to block their respective threads until there
/// is available capacity.
///
/// Recommended to be a power of 2.
pub const DEFAULT_BUFFERED_LINES_LIMIT: usize = 128_000;
"""


# Associated `pub const`s, cut before the `impl` block closes.
# Source: https://github.com/tokio-rs/tracing
#   commit 9d0e557728ecb91e467fc29dfe738b9f28cf6684
#   tracing-appender/src/rolling.rs lines 535-557
#   MIT License, Copyright (c) 2019 Tokio Contributors
ROTATION = rb"""#[derive(Clone, Eq, PartialEq, Debug)]
pub struct Rotation(RotationKind);

#[derive(Clone, Eq, PartialEq, Debug)]
enum RotationKind {
    Minutely,
    Hourly,
    Daily,
    Weekly,
    Never,
}

impl Rotation {
    /// Provides a minutely rotation.
    pub const MINUTELY: Self = Self(RotationKind::Minutely);
    /// Provides an hourly rotation.
    pub const HOURLY: Self = Self(RotationKind::Hourly);
    /// Provides a daily rotation.
    pub const DAILY: Self = Self(RotationKind::Daily);
    /// Provides a weekly rotation that rotates every Sunday at midnight UTC.
    pub const WEEKLY: Self = Self(RotationKind::Weekly);
    /// Provides a rotation that never rotates.
    pub const NEVER: Self = Self(RotationKind::Never);
"""


# A `pub(crate)` function and the `#[cfg(test)]` module that tests it.
# Source: https://github.com/BurntSushi/ripgrep
#   commit 3fce3b5bb0236da2df6d99672afb8a719642eca7
#   crates/regex/src/ban.rs lines 1-83 (the whole file)
#   MIT License (or the Unlicense), Copyright (c) 2015 Andrew Gallant
BAN = rb"""use regex_syntax::hir::{
    self, ClassBytesRange, ClassUnicodeRange, Hir, HirKind,
};

use crate::error::{Error, ErrorKind};

/// Returns an error when a sub-expression in `expr` must match `byte`.
pub(crate) fn check(expr: &Hir, byte: u8) -> Result<(), Error> {
    assert!(byte.is_ascii(), "ban byte must be ASCII");
    let ch = char::from(byte);
    let invalid = || Err(Error::new(ErrorKind::Banned(byte)));
    match *expr.kind() {
        HirKind::Empty => {}
        HirKind::Literal(hir::Literal(ref lit)) => {
            if lit.iter().find(|&&b| b == byte).is_some() {
                return invalid();
            }
        }
        HirKind::Class(hir::Class::Unicode(ref cls)) => {
            if cls.ranges().iter().map(|r| r.len()).sum::<usize>() == 1 {
                let contains =
                    |r: &&ClassUnicodeRange| r.start() <= ch && ch <= r.end();
                if cls.ranges().iter().find(contains).is_some() {
                    return invalid();
                }
            }
        }
        HirKind::Class(hir::Class::Bytes(ref cls)) => {
            if cls.ranges().iter().map(|r| r.len()).sum::<usize>() == 1 {
                let contains = |r: &&ClassBytesRange| {
                    r.start() <= byte && byte <= r.end()
                };
                if cls.ranges().iter().find(contains).is_some() {
                    return invalid();
                }
            }
        }
        HirKind::Look(_) => {}
        HirKind::Repetition(ref x) => check(&x.sub, byte)?,
        HirKind::Capture(ref x) => check(&x.sub, byte)?,
        HirKind::Concat(ref xs) => {
            for x in xs.iter() {
                check(x, byte)?;
            }
        }
        HirKind::Alternation(ref xs) => {
            for x in xs.iter() {
                check(x, byte)?;
            }
        }
    };
    Ok(())
}

#[cfg(test)]
mod tests {
    use regex_syntax::Parser;

    /// Returns true when the given pattern is detected to contain the given
    /// banned byte.
    fn check(pattern: &str, byte: u8) -> bool {
        let hir = Parser::new().parse(pattern).unwrap();
        super::check(&hir, byte).is_err()
    }

    #[test]
    fn various() {
        assert!(check(r"\x00", 0));
        assert!(check(r"a\x00", 0));
        assert!(check(r"\x00b", 0));
        assert!(check(r"a\x00b", 0));
        assert!(check(r"\x00|ab", 0));
        assert!(check(r"ab|\x00", 0));
        assert!(check(r"\x00?", 0));
        assert!(check(r"(\x00)", 0));

        assert!(check(r"[\x00]", 0));
        assert!(check(r"[^[^\x00]]", 0));

        assert!(!check(r"[^\x00]", 0));
        assert!(!check(r"[\x00a]", 0));
    }
}
"""


# A public trait with required and provided methods, and an impl of it.
# Source: https://github.com/BurntSushi/ripgrep
#   commit 3fce3b5bb0236da2df6d99672afb8a719642eca7
#   crates/searcher/src/sink.rs lines 1-50
#   MIT License (or the Unlicense), Copyright (c) 2015 Andrew Gallant
SINK = rb"""use std::io;

use grep_matcher::LineTerminator;

use crate::{
    lines::LineIter,
    searcher::{ConfigError, Searcher},
};

/// A trait that describes errors that can be reported by searchers and
/// implementations of `Sink`.
///
/// Unless you have a specialized use case, you probably don't need to
/// implement this trait explicitly. It's likely that using `std::io::Error`
/// (which implements this trait) for your error type is good enough,
/// largely because most errors that occur during search will likely be an
/// `std::io::Error`.
pub trait SinkError: Sized {
    /// A constructor for converting any value that satisfies the
    /// `std::fmt::Display` trait into an error.
    fn error_message<T: std::fmt::Display>(message: T) -> Self;

    /// A constructor for converting I/O errors that occur while searching into
    /// an error of this type.
    ///
    /// By default, this is implemented via the `error_message` constructor.
    fn error_io(err: io::Error) -> Self {
        Self::error_message(err)
    }

    /// A constructor for converting configuration errors that occur while
    /// building a searcher into an error of this type.
    ///
    /// By default, this is implemented via the `error_message` constructor.
    fn error_config(err: ConfigError) -> Self {
        Self::error_message(err)
    }
}

/// An `std::io::Error` can be used as an error for `Sink` implementations out
/// of the box.
impl SinkError for io::Error {
    fn error_message<T: std::fmt::Display>(message: T) -> io::Error {
        io::Error::new(io::ErrorKind::Other, message.to_string())
    }

    fn error_io(err: io::Error) -> io::Error {
        err
    }
}
"""


# A crate root re-exporting through one `pub use` tree, and its modules.
# Source: https://github.com/BurntSushi/ripgrep
#   commit 3fce3b5bb0236da2df6d99672afb8a719642eca7
#   crates/searcher/src/lib.rs lines 86-106
#   MIT License (or the Unlicense), Copyright (c) 2015 Andrew Gallant
SEARCHER_LIB = rb"""pub use crate::{
    lines::{LineIter, LineStep},
    searcher::{
        BinaryDetection, ConfigError, Encoding, MmapChoice, Searcher,
        SearcherBuilder,
    },
    sink::{
        Sink, SinkContext, SinkContextKind, SinkError, SinkFinish, SinkMatch,
        sinks,
    },
};

#[macro_use]
mod macros;

mod line_buffer;
mod lines;
mod searcher;
mod sink;
#[cfg(test)]
mod testutil;
"""


# Crates re-exported under aliases with `pub extern crate`.
# Source: https://github.com/BurntSushi/ripgrep
#   commit 3fce3b5bb0236da2df6d99672afb8a719642eca7
#   crates/grep/src/lib.rs lines 15-21
#   MIT License (or the Unlicense), Copyright (c) 2015 Andrew Gallant
GREP_LIB = rb"""pub extern crate grep_cli as cli;
pub extern crate grep_matcher as matcher;
#[cfg(feature = "pcre2")]
pub extern crate grep_pcre2 as pcre2;
pub extern crate grep_printer as printer;
pub extern crate grep_regex as regex;
pub extern crate grep_searcher as searcher;
"""


# Private statics and a `macro_rules!` macro whose body calls functions.
# Source: https://github.com/BurntSushi/ripgrep
#   commit 3fce3b5bb0236da2df6d99672afb8a719642eca7
#   crates/core/messages.rs lines 18-67
#   MIT License (or the Unlicense), Copyright (c) 2015 Andrew Gallant
MESSAGES = rb"""use std::sync::atomic::{AtomicBool, Ordering};

/// When false, "messages" will not be printed.
static MESSAGES: AtomicBool = AtomicBool::new(false);
/// When false, "messages" related to ignore rules will not be printed.
static IGNORE_MESSAGES: AtomicBool = AtomicBool::new(false);
/// Flipped to true when an error message is printed.
static ERRORED: AtomicBool = AtomicBool::new(false);

/// Like eprintln, but locks stdout to prevent interleaving lines.
///
/// This locks stdout, not stderr, even though this prints to stderr. This
/// avoids the appearance of interleaving output when stdout and stderr both
/// correspond to a tty.
#[macro_export]
macro_rules! eprintln_locked {
    ($($tt:tt)*) => {{
        {
            use std::io::Write;

            // This is a bit of an abstraction violation because we explicitly
            // lock stdout before printing to stderr. This avoids interleaving
            // lines within ripgrep because `search_parallel` uses `termcolor`,
            // which accesses the same stdout lock when writing lines.
            let stdout = std::io::stdout().lock();
            let mut stderr = std::io::stderr().lock();
            // We specifically ignore any errors here. One plausible error we
            // can get in some cases is a broken pipe error. And when that
            // occurs, we should exit gracefully. Otherwise, just abort with
            // an error code because there isn't much else we can do.
            //
            // See: https://github.com/BurntSushi/ripgrep/issues/1966
            if let Err(err) = write!(stderr, "rg: ") {
                if err.kind() == std::io::ErrorKind::BrokenPipe {
                    std::process::exit(0);
                } else {
                    std::process::exit(2);
                }
            }
            if let Err(err) = writeln!(stderr, $($tt)*) {
                if err.kind() == std::io::ErrorKind::BrokenPipe {
                    std::process::exit(0);
                } else {
                    std::process::exit(2);
                }
            }
            drop(stdout);
        }
    }}
}
"""


# A glob `pub use` beside a named one.
# Source: https://github.com/tokio-rs/tracing
#   commit 9d0e557728ecb91e467fc29dfe738b9f28cf6684
#   tracing/src/subscriber.rs lines 1-6
#   MIT License, Copyright (c) 2019 Tokio Contributors
SUBSCRIBER = rb"""//! Collects and records trace data.
pub use tracing_core::subscriber::*;

#[cfg(feature = "std")]
#[cfg_attr(docsrs, doc(cfg(feature = "std")))]
pub use tracing_core::dispatcher::DefaultGuard;
"""


# `pub(super)` module declarations and a private static.
# Source: https://github.com/BurntSushi/ripgrep
#   commit 3fce3b5bb0236da2df6d99672afb8a719642eca7
#   crates/core/flags/complete/mod.rs lines 1-10 (the whole file)
#   MIT License (or the Unlicense), Copyright (c) 2015 Andrew Gallant
COMPLETE = rb"""/*!
Modules for generating completions for various shells.
*/

static ENCODINGS: &'static str = include_str!("encodings.sh");

pub(super) mod bash;
pub(super) mod fish;
pub(super) mod powershell;
pub(super) mod zsh;
"""


# A `pub(in path)` struct.
# Source: https://github.com/tokio-rs/tracing
#   commit 9d0e557728ecb91e467fc29dfe738b9f28cf6684
#   tracing-subscriber/src/fmt/writer.rs lines 677-680
#   MIT License, Copyright (c) 2019 Tokio Contributors
WRITE_ADAPTOR = rb"""#[cfg(any(feature = "json", feature = "time"))]
pub(in crate::fmt) struct WriteAdaptor<'a> {
    fmt_write: &'a mut dyn fmt::Write,
}
"""


# Restricted `pub(crate) use` re-exports, named and glob.
# Source: https://github.com/tokio-rs/tracing
#   commit 9d0e557728ecb91e467fc29dfe738b9f28cf6684
#   tracing-subscriber/src/sync.rs lines 10-17
#   MIT License, Copyright (c) 2019 Tokio Contributors
SYNC = rb"""#[allow(unused_imports)] // may be used later;
pub(crate) use std::sync::{LockResult, PoisonError, TryLockResult};

#[cfg(not(feature = "parking_lot"))]
pub(crate) use std::sync::{RwLock, RwLockReadGuard, RwLockWriteGuard};

#[cfg(feature = "parking_lot")]
pub(crate) use self::parking_lot_impl::*;
"""


# A `pub(self)` method, cut before its `impl` block closes.
# Source: https://github.com/tokio-rs/tokio
#   commit ce685ee6916549ed7e52dbfd5430858bbdc734d3
#   tokio/src/runtime/time/mod.rs lines 289-294
#   MIT License, Copyright (c) Tokio Contributors
TIME_HANDLE = rb"""impl Handle {
    pub(self) fn process(&self, clock: &Clock) {
        let now = self.time_source().now(clock);

        self.process_at_time(now);
    }
"""


# Re-exports at the top of a module and inside an inline `pub mod`.
# Source: https://github.com/tokio-rs/axum
#   commit 86aa6153e47b7862737acdcfe3a0eb3a162b939a
#   axum/src/middleware/mod.rs lines 1-33
#   MIT License, Copyright (c) 2019-2025 axum Contributors
MIDDLEWARE = rb"""//! Utilities for writing middleware
//!
#![doc = include_str!("../docs/middleware.md")]

mod from_extractor;
mod from_fn;
mod map_request;
mod map_response;
mod response_axum_body;

pub use self::from_extractor::{
    from_extractor, from_extractor_with_state, FromExtractor, FromExtractorLayer,
};
pub use self::from_fn::{from_fn, from_fn_with_state, FromFn, FromFnLayer, Next};
pub use self::map_request::{
    map_request, map_request_with_state, IntoMapRequestResult, MapRequest, MapRequestLayer,
};
pub use self::map_response::{
    map_response, map_response_with_state, MapResponse, MapResponseLayer,
};
pub use self::response_axum_body::{
    ResponseAxumBody, ResponseAxumBodyFuture, ResponseAxumBodyLayer,
};
pub use crate::extension::AddExtension;

pub mod future {
    //! Future types.

    pub use super::from_extractor::ResponseFuture as FromExtractorResponseFuture;
    pub use super::from_fn::ResponseFuture as FromFnResponseFuture;
    pub use super::map_request::ResponseFuture as MapRequestResponseFuture;
    pub use super::map_response::ResponseFuture as MapResponseResponseFuture;
}
"""  # noqa: E501


# `pub` enums inside a private inline module.
# Source: https://github.com/tokio-rs/axum
#   commit 86aa6153e47b7862737acdcfe3a0eb3a162b939a
#   axum-core/src/extract/mod.rs lines 7-39
#   MIT License, Copyright (c) 2019-2025 axum Contributors
EXTRACT = rb"""use crate::{body::Body, response::IntoResponse};
use http::request::Parts;
use std::convert::Infallible;
use std::future::Future;

pub mod rejection;

mod default_body_limit;
mod from_ref;
mod option;
mod request_parts;
mod tuple;

pub(crate) use self::default_body_limit::DefaultBodyLimitKind;
pub use self::{
    default_body_limit::DefaultBodyLimit,
    from_ref::FromRef,
    option::{OptionalFromRequest, OptionalFromRequestParts},
};

/// Type alias for [`http::Request`] whose body type defaults to [`Body`], the most common body
/// type used with axum.
pub type Request<T = Body> = http::Request<T>;

mod private {
    #[allow(clippy::empty_enums)] // We cannot use `!` yet in our MSRV.
    #[derive(Debug, Clone, Copy)]
    pub enum ViaParts {}

    #[allow(clippy::empty_enums)] // We cannot use `!` yet in our MSRV.
    #[derive(Debug, Clone, Copy)]
    pub enum ViaRequest {}
}
"""  # noqa: E501


# `pub` fields of a `pub(crate)` struct.
# Source: https://github.com/BurntSushi/ripgrep
#   commit 3fce3b5bb0236da2df6d99672afb8a719642eca7
#   crates/matcher/tests/util.rs lines 1-24
#   MIT License (or the Unlicense), Copyright (c) 2015 Andrew Gallant
MATCHER_UTIL = rb"""use std::collections::HashMap;

use {
    grep_matcher::{Captures, Match, Matcher, NoCaptures, NoError},
    regex::bytes::{CaptureLocations, Regex},
};

#[derive(Debug)]
pub(crate) struct RegexMatcher {
    pub re: Regex,
    pub names: HashMap<String, usize>,
}

impl RegexMatcher {
    pub(crate) fn new(re: Regex) -> RegexMatcher {
        let mut names = HashMap::new();
        for (i, optional_name) in re.capture_names().enumerate() {
            if let Some(name) = optional_name {
                names.insert(name.to_string(), i);
            }
        }
        RegexMatcher { re, names }
    }
}
"""


# `macro_rules!` macros with no `#[macro_export]`.
# Source: https://github.com/tokio-rs/tracing
#   commit 9d0e557728ecb91e467fc29dfe738b9f28cf6684
#   tracing-subscriber/src/macros.rs lines 1-28 (the whole file)
#   MIT License, Copyright (c) 2019 Tokio Contributors
TRACING_MACROS = rb"""#[cfg(feature = "std")]
macro_rules! try_lock {
    ($lock:expr) => {
        try_lock!($lock, else return)
    };
    ($lock:expr, else $els:expr) => {
        if let ::core::result::Result::Ok(l) = $lock {
            l
        } else if std::thread::panicking() {
            $els
        } else {
            panic!("lock poisoned")
        }
    };
}

macro_rules! feature {
    (
        #![$meta:meta]
        $($item:item)*
    ) => {
        $(
            #[cfg($meta)]
            #[cfg_attr(docsrs, doc(cfg($meta)))]
            $item
        )*
    }
}
"""


def test_a_rust_file_is_rust() -> None:
    assert language_of("crates/regex/src/ban.rs") == "rust"


def test_a_pub_use_exports_each_name_under_its_alias() -> None:
    assert _exports(LEVEL) == {("LevelFilter", 7), ("ParseError", 7)}


def test_a_use_tree_imports_each_name_it_brings_in_under_its_own_name() -> None:
    assert _imports(LEVEL) == {
        ("Interest", 2, "tracing_core::subscriber"),
        ("Subscriber", 2, "tracing_core::subscriber"),
        ("Metadata", 3, "tracing_core"),
        ("LevelFilter", 7, "tracing_core::metadata"),
        ("ParseLevelFilterError", 7, "tracing_core::metadata"),
    }
    statements = {s.signature for s in _of(SymbolKind.IMPORT, LEVEL) if s.line == 7}
    assert statements == {
        "pub use tracing_core::metadata::{LevelFilter, ParseLevelFilterError as "
        "ParseError};"
    }


def test_methods_of_a_trait_impl_are_methods_and_not_exports() -> None:
    assert {(name, line, detail) for name, line, detail, _ in _definitions(LEVEL)} == {
        ("register_callsite", 12, "method"),
        ("enabled", 20, "method"),
        ("max_level_hint", 24, "method"),
    }
    assert {("always", 14), ("never", 16), ("level", 13), ("Some", 25)} <= (
        _references(LEVEL)
    )


def test_a_pub_const_is_exported_and_never_defined() -> None:
    assert _exports(NON_BLOCKING) == {("DEFAULT_BUFFERED_LINES_LIMIT", 21)}
    assert _definitions(NON_BLOCKING) == set()
    assert ("Write", 5, "std::io") in _imports(NON_BLOCKING)
    assert ("bounded", 3, "crossbeam_channel") in _imports(NON_BLOCKING)


def test_a_file_cut_mid_impl_still_yields_what_parsed() -> None:
    """tree-sitter does not refuse a broken file: the struct, the private enum and the
    associated constants before the missing `}` are all still found."""
    assert _definitions(ROTATION) == {
        ("Rotation", 2, "struct", "pub struct Rotation"),
        ("RotationKind", 5, "enum", "enum RotationKind"),
    }
    assert _exports(ROTATION) == {
        ("Rotation", 2),
        ("MINUTELY", 15),
        ("HOURLY", 17),
        ("DAILY", 19),
        ("WEEKLY", 21),
        ("NEVER", 23),
    }


def test_pub_crate_is_not_an_export() -> None:
    assert _definitions(BAN) == {
        (
            "check",
            8,
            "function",
            "pub(crate) fn check(expr: &Hir, byte: u8) -> Result<(), Error>",
        )
    }
    assert _exports(BAN) == set()


def test_a_cfg_test_module_and_its_test_functions_contribute_nothing() -> None:
    """The module re-defines `check` and calls `Parser::new`; neither is seen."""
    lines = {s.line for s in extract("src/file.rs", BAN)}
    assert max(lines) <= 53
    assert ("Parser", 57, "regex_syntax") not in _imports(BAN)
    assert {name for name, _ in _references(BAN)}.isdisjoint({"parse", "unwrap"})


def test_self_in_a_use_list_imports_the_module_itself() -> None:
    assert ("hir", 2, "regex_syntax") in _imports(BAN)
    assert ("HirKind", 2, "regex_syntax::hir") in _imports(BAN)


def test_a_macro_invocation_is_a_reference_to_the_macro() -> None:
    assert ("assert", 9) in _references(BAN)
    assert {("check", 39), ("invalid", 16), ("Ok", 52)} <= _references(BAN)


def test_a_public_trait_its_methods_and_an_impl_of_it() -> None:
    assert _definitions(SINK) == {
        ("SinkError", 18, "trait", "pub trait SinkError: Sized"),
        (
            "error_message",
            21,
            "method",
            "fn error_message<T: std::fmt::Display>(message: T) -> Self;",
        ),
        ("error_io", 27, "method", "fn error_io(err: io::Error) -> Self"),
        ("error_config", 35, "method", "fn error_config(err: ConfigError) -> Self"),
        (
            "error_message",
            43,
            "method",
            "fn error_message<T: std::fmt::Display>(message: T) -> io::Error",
        ),
        ("error_io", 47, "method", "fn error_io(err: io::Error) -> io::Error"),
    }
    assert _exports(SINK) == {("SinkError", 18)}
    assert {("error_message", 28), ("error_message", 36), ("new", 44)} <= (
        _references(SINK)
    )


def test_a_crate_root_exports_every_name_its_pub_use_tree_names() -> None:
    exports = {name for name, _ in _exports(SEARCHER_LIB)}
    assert exports == {
        "LineIter",
        "LineStep",
        "BinaryDetection",
        "ConfigError",
        "Encoding",
        "MmapChoice",
        "Searcher",
        "SearcherBuilder",
        "Sink",
        "SinkContext",
        "SinkContextKind",
        "SinkError",
        "SinkFinish",
        "SinkMatch",
        "sinks",
    }
    assert ("SinkMatch", 8, "crate::sink") in _imports(SEARCHER_LIB)


def test_module_declarations_are_definitions_and_a_cfg_test_one_is_skipped() -> None:
    modules = {(name, line) for name, line, detail, _ in _definitions(SEARCHER_LIB)}
    assert modules == {
        ("macros", 14),
        ("line_buffer", 16),
        ("lines", 17),
        ("searcher", 18),
        ("sink", 19),
    }


def test_pub_extern_crate_imports_the_crate_and_exports_its_alias() -> None:
    assert _imports(GREP_LIB) >= {
        ("grep_cli", 1, "grep_cli"),
        ("grep_searcher", 7, "grep_searcher"),
    }
    assert _exports(GREP_LIB) == {
        ("cli", 1),
        ("matcher", 2),
        ("pcre2", 4),
        ("printer", 5),
        ("regex", 6),
        ("searcher", 7),
    }


def test_private_statics_export_nothing_and_a_macro_body_is_opaque() -> None:
    assert _definitions(MESSAGES) == {
        ("eprintln_locked", 16, "macro", "macro_rules! eprintln_locked"),
    }
    # `#[macro_export]` puts the macro at the crate root; the statics stay private.
    assert _exports(MESSAGES) == {("eprintln_locked", 16)}
    # `std::process::exit` and `stdout` are called only inside the macro's rules.
    assert {name for name, _ in _references(MESSAGES)} == {"new"}


def test_a_glob_pub_use_names_nothing_and_exports_nothing() -> None:
    assert _exports(SUBSCRIBER) == {("DefaultGuard", 6)}
    assert ("*", 2, "tracing_core::subscriber") in _imports(SUBSCRIBER)


def test_pub_super_pub_in_and_pub_self_are_not_exports() -> None:
    assert {name for name, *_ in _definitions(COMPLETE)} == {
        "bash",
        "fish",
        "powershell",
        "zsh",
    }
    assert _exports(COMPLETE) == set()
    assert {name for name, *_ in _definitions(WRITE_ADAPTOR)} == {"WriteAdaptor"}
    assert _exports(WRITE_ADAPTOR) == set()
    assert {(n, line, d) for n, line, d, _ in _definitions(TIME_HANDLE)} == {
        ("process", 2, "method")
    }
    assert _exports(TIME_HANDLE) == set()


def test_a_restricted_pub_crate_use_imports_but_exports_nothing() -> None:
    assert _exports(SYNC) == set()
    assert {
        ("LockResult", 2, "std::sync"),
        ("RwLockWriteGuard", 5, "std::sync"),
        ("*", 8, "self::parking_lot_impl"),
    } <= _imports(SYNC)


def test_a_pub_item_inside_a_private_module_is_not_exported() -> None:
    definitions = {(n, line, d) for n, line, d, _ in _definitions(EXTRACT)}
    assert {("private", 25, "module"), ("ViaParts", 28, "enum")} <= definitions
    assert ("ViaRequest", 32, "enum") in definitions
    names = {name for name, _ in _exports(EXTRACT)}
    assert names.isdisjoint({"private", "ViaParts", "ViaRequest"})
    assert {"rejection", "Request", "DefaultBodyLimit", "FromRef"} <= names


def test_a_pub_field_of_a_pub_crate_struct_is_not_exported() -> None:
    assert ("RegexMatcher", 9, "struct", "pub(crate) struct RegexMatcher") in (
        _definitions(MATCHER_UTIL)
    )
    assert _exports(MATCHER_UTIL) == set()


def test_re_exports_inside_a_pub_module_are_exported() -> None:
    exports = _exports(MIDDLEWARE)
    assert {
        ("future", 26),
        ("FromExtractorResponseFuture", 29),
        ("FromFnResponseFuture", 30),
        ("MapRequestResponseFuture", 31),
        ("MapResponseResponseFuture", 32),
        ("Next", 14),
        ("AddExtension", 24),
    } <= exports
    # The private `mod` declarations on lines 5-9 are not.
    assert {line for _, line in exports}.isdisjoint(range(5, 10))


def test_a_macro_without_macro_export_is_defined_but_not_exported() -> None:
    assert {(n, line, d) for n, line, d, _ in _definitions(TRACING_MACROS)} == {
        ("try_lock", 2, "macro"),
        ("feature", 17, "macro"),
    }
    assert _exports(TRACING_MACROS) == set()
