"""Java symbol extraction, held to real source rather than to examples written for it.

Every excerpt below is copied verbatim from an MIT-licensed Java repository, at the
commit and lines its comment names, and is only parsed here, never compiled or run.
Between them they hold what a Java extractor has to get right: a definition's line
is its name's and not its first annotation's, `public` and `protected` export and
package-private does not, interface and annotation members and enum constants are
public without saying so, a member is exported only when every type around it is,
fields and constants are exports and never definitions, wildcard and static imports,
and a file cut mid-method still yields what parsed.
"""

from __future__ import annotations

from mcgyvr.orchestrator.symbols import Symbol, SymbolKind, extract, language_of


def _of(kind: SymbolKind, source: bytes) -> list[Symbol]:
    return [s for s in extract("src/main/java/File.java", source) if s.kind is kind]


def _definitions(source: bytes) -> set[tuple[str, int, str]]:
    return {(s.name, s.line, s.detail) for s in _of(SymbolKind.DEFINITION, source)}


def _signature(source: bytes, name: str, line: int) -> str:
    (signature,) = {
        s.signature
        for s in _of(SymbolKind.DEFINITION, source)
        if (s.name, s.line) == (name, line)
    }
    return signature


def _exports(source: bytes) -> set[tuple[str, int]]:
    return {(s.name, s.line) for s in _of(SymbolKind.EXPORT, source)}


def _imports(source: bytes) -> set[tuple[str, int, str]]:
    return {(s.name, s.line, s.detail) for s in _of(SymbolKind.IMPORT, source)}


def _references(source: bytes) -> set[tuple[str, int]]:
    return {(s.name, s.line) for s in _of(SymbolKind.REFERENCE, source)}


# Static and static-wildcard imports, and an interface's abstract, default and
# static methods.
# Source: https://github.com/mockito/mockito
#   commit 220c594adceebf92a0d06e2fb1e4398b25344d46
#   mockito-core/src/main/java/org/mockito/internal/creation/bytebuddy/
#   BytecodeGenerator.java lines 1-34 (the whole file)
#   MIT License, Copyright (c) 2007 Mockito contributors
BYTECODE_GENERATOR = rb"""/*
 * Copyright (c) 2016 Mockito contributors
 * This program is made available under the terms of the MIT License.
 */
package org.mockito.internal.creation.bytebuddy;

import net.bytebuddy.description.method.MethodDescription;
import net.bytebuddy.matcher.ElementMatcher;

import static net.bytebuddy.matcher.ElementMatchers.*;
import static net.bytebuddy.matcher.ElementMatchers.named;

public interface BytecodeGenerator {

    <T> Class<? extends T> mockClass(MockFeatures<T> features);

    void mockClassConstruction(Class<?> type);

    void mockClassStatic(Class<?> type);

    default void clearAllCaches() {}

    static ElementMatcher<MethodDescription> isGroovyMethod(boolean inline) {
        ElementMatcher.Junction<MethodDescription> matcher =
                isDeclaredBy(named("groovy.lang.GroovyObjectSupport"))
                        .or(isAnnotatedWith(named("groovy.transform.Internal")));
        if (inline) {
            return matcher.or(
                    named("$getStaticMetaClass").and(returns(named("groovy.lang.MetaClass"))));
        } else {
            return matcher;
        }
    }
}
"""


# Annotated methods, protected abstract methods and a private field.
# Source: https://github.com/mockito/mockito
#   commit 220c594adceebf92a0d06e2fb1e4398b25344d46
#   mockito-core/src/main/java/org/mockito/internal/matchers/CompareTo.java
#   lines 1-40 (the whole file)
#   MIT License, Copyright (c) 2007 Mockito contributors
COMPARE_TO = rb"""/*
 * Copyright (c) 2007 Mockito contributors
 * This program is made available under the terms of the MIT License.
 */
package org.mockito.internal.matchers;

import java.io.Serializable;

import org.mockito.ArgumentMatcher;

public abstract class CompareTo<T extends Comparable<T>>
        implements ArgumentMatcher<T>, Serializable {
    private final T wanted;

    public CompareTo(T value) {
        this.wanted = value;
    }

    @Override
    public final boolean matches(T actual) {
        if (actual == null) {
            return false;
        }
        if (!actual.getClass().isInstance(wanted)) {
            return false;
        }

        int result = actual.compareTo(wanted);
        return matchResult(result);
    }

    @Override
    public final String toString() {
        return getName() + "(" + wanted + ")";
    }

    protected abstract String getName();

    protected abstract boolean matchResult(int result);
}
"""


# An annotated interface with a constant, a default method and an abstract one.
# Source: https://github.com/mockito/mockito
#   commit 220c594adceebf92a0d06e2fb1e4398b25344d46
#   mockito-core/src/main/java/org/mockito/plugins/ValueRenderer.java
#   lines 1-40 (the whole file)
#   MIT License, Copyright (c) 2007 Mockito contributors
VALUE_RENDERER = rb"""/*
 * Copyright (c) 2026 Mockito contributors
 * This program is made available under the terms of the MIT License.
 */
package org.mockito.plugins;

import org.jspecify.annotations.NullMarked;
import org.jspecify.annotations.Nullable;

/**
 * Prints a Java object value in a way humans can read it neatly.
 * Used for printing arguments in verification errors.
 *
 * @since 5.25.0
 */
@NullMarked
public interface ValueRenderer {
    int DEFAULT_PRIORITY = 0;

    /**
     * Determines the order in which renders will be tried, if multiple renderers are available.
     * A higher number will be tried first.  Renderers with the same priority will be ordered be classname.
     * <p>
     * An internal fallback renderer will always be tried last, which can always render any object.
     *
     * @return a number indicating the priority of this renderer.
     */
    default int getPluginPriority() {
        return DEFAULT_PRIORITY;
    }

    /**
     * Prints given value so that it is neatly readable by humans.
     * Must handle explosive toString() implementations.
     * If a renderer implementation determines it cannot render this object, it indicates this by returning null.
     *
     * @return A string rendering of {@code value}, or {@code null} if the current renderer does not support this type of value.
     */
    @Nullable String print(@Nullable final Object value);
}
"""  # noqa: E501


# An enum and its constants, between long Javadoc comments.
# Source: https://github.com/mockito/mockito
#   commit 220c594adceebf92a0d06e2fb1e4398b25344d46
#   mockito-core/src/main/java/org/mockito/quality/Strictness.java
#   lines 1-87 (the whole file)
#   MIT License, Copyright (c) 2007 Mockito contributors
STRICTNESS = rb"""/*
 * Copyright (c) 2017 Mockito contributors
 * This program is made available under the terms of the MIT License.
 */
package org.mockito.quality;

import org.mockito.MockitoSession;
import org.mockito.exceptions.misusing.PotentialStubbingProblem;
import org.mockito.exceptions.misusing.UnnecessaryStubbingException;
import org.mockito.internal.junit.JUnitRule;
import org.mockito.junit.MockitoJUnit;
import org.mockito.junit.MockitoJUnitRunner;
import org.mockito.junit.MockitoRule;

/**
 * Configures the "strictness" of Mockito, affecting the behavior of stubbings and verification.
 * "Strict stubbing" is a new feature in Mockito 2 that drives cleaner tests and better productivity.
 * The easiest way to leverage it is via Mockito's JUnit support ({@link MockitoJUnit}) or Mockito Session ({@link MockitoSession}).
 * <p>
 * How strictness influences the behavior of the test?
 * <ol>
 *     <li>{@link Strictness#STRICT_STUBS} - ensures clean tests, reduces test code duplication, improves debuggability.
 *       Best combination of flexibility and productivity. Highly recommended.
 *       Planned as default for Mockito v4.
 *       Enable it via {@link MockitoRule}, {@link MockitoJUnitRunner} or {@link MockitoSession}.
 *       See {@link #STRICT_STUBS} for the details.</li>
 *     <li>{@link Strictness#LENIENT} - no added behavior.
 *       The default of Mockito 1.x.
 *       Recommended only if you cannot use {@link #STRICT_STUBS}</li>
 *     <li>{@link Strictness#WARN} - cleaner tests but only if you read the console output.
 *       Reports console warnings about unused stubs
 *       and stubbing argument mismatch (see {@link org.mockito.quality.MockitoHint}).
 *       The default behavior of Mockito 2.x when {@link JUnitRule} or {@link MockitoJUnitRunner} are used.
 *       Recommended if you cannot use {@link #STRICT_STUBS}.
 *       Introduced originally with Mockito 2 because console warnings was the only compatible way of adding such feature.</li>
 * </ol>
 *
 * @since 2.3.0
 */
public enum Strictness {

    /**
     * No extra strictness. Mockito 1.x behavior.
     * Recommended only if you cannot use {@link #STRICT_STUBS}.
     * <p>
     * For more information see {@link Strictness}.
     *
     * @since 2.3.0
     */
    LENIENT,

    /**
     * Helps keeping tests clean and improves debuggability only if you read the console output.
     * Extra warnings emitted to the console, see {@link MockitoHint}.
     * Default Mockito 2.x behavior.
     * Recommended only if you cannot use {@link #STRICT_STUBS} because console output is ignored most of the time.
     * <p>
     * For more information see {@link Strictness}.
     *
     * @since 2.3.0
     */
    WARN,

    /**
     * Ensures clean tests, reduces test code duplication, improves debuggability.
     * Offers best combination of flexibility and productivity.
     * Highly recommended.
     * Enable it via our JUnit support ({@link MockitoJUnit}) or {@link MockitoSession}.
     * <p>
     * Adds following behavior:
     *  <ul>
     *      <li>Improved productivity: the test fails early when code under test invokes
     *          stubbed method with different arguments (see {@link PotentialStubbingProblem}).</li>
     *      <li>Cleaner tests without unnecessary stubbings:
     *          the test fails when unused stubs are present (see {@link UnnecessaryStubbingException}).</li>
     *      <li>Cleaner, more DRY tests ("Don't Repeat Yourself"):
     *          If you use {@link org.mockito.Mockito#verifyNoMoreInteractions(Object...)}
     *          you no longer need to explicitly verify stubbed invocations.
     *          They are automatically verified for you.</li>
     *  </ul>
     *
     * For more information see {@link Strictness}.
     *
     * @since 2.3.0
     */
    STRICT_STUBS;
}
"""  # noqa: E501


# A package-private class with protected, private and package-private members,
# and an anonymous class.
# Source: https://github.com/mockito/mockito
#   commit 220c594adceebf92a0d06e2fb1e4398b25344d46
#   mockito-core/src/main/java/org/mockito/internal/junit/JUnitSessionStore.java
#   lines 1-72 (the whole file)
#   MIT License, Copyright (c) 2007 Mockito contributors
SESSION_STORE = rb"""/*
 * Copyright (c) 2020 Mockito contributors
 * This program is made available under the terms of the MIT License.
 */
package org.mockito.internal.junit;

import org.junit.runners.model.Statement;
import org.mockito.Mockito;
import org.mockito.MockitoAnnotations;
import org.mockito.MockitoSession;
import org.mockito.internal.session.MockitoSessionLoggerAdapter;
import org.mockito.plugins.MockitoLogger;
import org.mockito.quality.Strictness;

class JUnitSessionStore {

    private final MockitoLogger logger;
    private MockitoSession session;
    protected Strictness strictness;

    JUnitSessionStore(MockitoLogger logger, Strictness strictness) {
        this.logger = logger;
        this.strictness = strictness;
    }

    Statement createStatement(final Statement base, final String methodName, final Object target) {
        return new Statement() {
            @Override
            public void evaluate() throws Throwable {
                AutoCloseable closeable;
                if (session == null) {
                    session =
                            Mockito.mockitoSession()
                                    .name(methodName)
                                    .strictness(strictness)
                                    .logger(new MockitoSessionLoggerAdapter(logger))
                                    .initMocks(target)
                                    .startMocking();
                    closeable = null;
                } else {
                    closeable = MockitoAnnotations.openMocks(target);
                }
                Throwable testFailure = evaluateSafely(base);
                session.finishMocking(testFailure);
                if (closeable != null) {
                    closeable.close();
                }
                if (testFailure != null) {
                    throw testFailure;
                }
            }

            private Throwable evaluateSafely(Statement base) {
                try {
                    base.evaluate();
                    return null;
                } catch (Throwable throwable) {
                    return throwable;
                }
            }
        };
    }

    void setStrictness(Strictness strictness) {
        this.strictness = strictness;
        // session is null when this method is called during initialization of
        // the @Rule field of the test class
        if (session != null) {
            session.setStrictness(strictness);
        }
    }
}
"""  # noqa: E501


# An annotation type with one element, under three annotations.
# Source: https://github.com/mockito/mockito
#   commit 220c594adceebf92a0d06e2fb1e4398b25344d46
#   mockito-extensions/mockito-junit-jupiter/src/main/java/org/mockito/junit/
#   jupiter/MockitoSettings.java lines 1-28 (the whole file)
#   MIT License, Copyright (c) 2007 Mockito contributors
MOCKITO_SETTINGS = rb"""/*
 * Copyright (c) 2018 Mockito contributors
 * This program is made available under the terms of the MIT License.
 */
package org.mockito.junit.jupiter;

import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.quality.Strictness;

import java.lang.annotation.Inherited;
import java.lang.annotation.Retention;

import static java.lang.annotation.RetentionPolicy.RUNTIME;

/**
 * Annotation that can configure Mockito as invoked by the {@link MockitoExtension}.
 */
@ExtendWith(MockitoExtension.class)
@Inherited
@Retention(RUNTIME)
public @interface MockitoSettings {

    /**
     * Configure the strictness used in this test.
     * @return The strictness to configure, by default {@link Strictness#STRICT_STUBS}
     */
    Strictness strictness() default Strictness.STRICT_STUBS;
}
"""


# A generic interface and an annotated interface nested in it.
# Source: https://github.com/mockito/mockito
#   commit 220c594adceebf92a0d06e2fb1e4398b25344d46
#   mockito-core/src/main/java/org/mockito/MockedStatic.java
#   lines 1-78 (the whole file)
#   MIT License, Copyright (c) 2007 Mockito contributors
MOCKED_STATIC = rb"""/*
 * Copyright (c) 2007 Mockito contributors
 * This program is made available under the terms of the MIT License.
 */
package org.mockito;

import static org.mockito.Mockito.times;

import org.mockito.stubbing.OngoingStubbing;
import org.mockito.verification.VerificationMode;

/**
 * Represents an active mock of a type's static methods. The mocking only affects the thread
 * on which this static mock was created and it is not safe to use this object from another
 * thread. The static mock is released when this object's {@link MockedStatic#close()} method
 * is invoked. If this object is never closed, the static mock will remain active on the
 * initiating thread. It is therefore recommended to create this object within a try-with-resources
 * statement unless when managed explicitly, for example by using a JUnit rule or extension.
 * <p>
 * If the {@link Mock} annotation is used on fields or method parameters of this type, a static mock
 * is created instead of a regular mock. The static mock is activated and released upon completing any
 * relevant test.
 *
 * @param <T> The type being mocked.
 */
public interface MockedStatic<T> extends ScopedMock {

    /**
     * See {@link Mockito#when(Object)}.
     */
    <S> OngoingStubbing<S> when(Verification verification);

    /**
     * See {@link Mockito#verify(Object)}.
     */
    default void verify(Verification verification) {
        verify(verification, times(1));
    }

    /**
     * See {@link Mockito#verify(Object, VerificationMode)}.
     */
    void verify(Verification verification, VerificationMode mode);

    /**
     * See {@link Mockito#reset(Object[])}.
     */
    void reset();

    /**
     * See {@link Mockito#clearInvocations(Object[])}.
     */
    void clearInvocations();

    /**
     * {@link Mockito#verifyNoMoreInteractions(Object...)}.
     */
    void verifyNoMoreInteractions();

    /**
     * See {@link Mockito#verifyNoInteractions(Object...)}.
     */
    void verifyNoInteractions();

    /**
     * Functional interface for a verification operation on a static mock.
     */
    @FunctionalInterface
    interface Verification {

        /**
         * Apply the verification operation.
         *
         * @throws Throwable any exception that may be thrown.
         */
        void apply() throws Throwable;
    }
}
"""  # noqa: E501


# A wildcard import, and a class cut mid-method so the file does not parse.
# Source: https://github.com/mockito/mockito
#   commit 220c594adceebf92a0d06e2fb1e4398b25344d46
#   mockito-core/src/main/java/org/mockito/internal/util/collections/
#   WeakIdentityMap.java lines 1-46
#   MIT License, Copyright (c) 2007 Mockito contributors
WEAK_IDENTITY_MAP = rb"""/*
 * Copyright (c) 2024 Mockito contributors
 * This program is made available under the terms of the MIT License.
 */
package org.mockito.internal.util.collections;

import java.lang.ref.ReferenceQueue;
import java.lang.ref.WeakReference;
import java.util.*;

/**
 * A weak-key map that uses identity ({@code ==}) rather than {@code hashCode()}/{@code equals()}
 * for key comparison. This avoids calling instrumented methods on mock instances during map
 * operations, which would cause infinite recursion. Stale entries whose keys have been
 * garbage-collected are cleaned up via a {@link ReferenceQueue}.
 *
 * <p>Internally, entries are bucketed by {@link System#identityHashCode} for O(1) amortized
 * lookups. Hash collisions (distinct objects sharing an identity hash code) are resolved by
 * linear scan within the bucket using {@code ==}. Lookups do not allocate.
 */
public class WeakIdentityMap<V> extends AbstractMap<Object, V> {

    private final Map<Integer, List<WeakEntry<V>>> delegate = new HashMap<>();
    private final ReferenceQueue<Object> queue = new ReferenceQueue<>();
    private int size;

    private void expungeStaleEntries() {
        WeakEntry<?> ref;
        while ((ref = (WeakEntry<?>) queue.poll()) != null) {
            int hash = ref.hashCode;
            List<WeakEntry<V>> bucket = delegate.get(hash);
            if (bucket != null) {
                if (bucket.remove(ref)) {
                    size--;
                    if (bucket.isEmpty()) {
                        delegate.remove(hash);
                    }
                }
            }
        }
    }

    @Override
    public V get(Object key) {
        expungeStaleEntries();
        List<WeakEntry<V>> bucket = delegate.get(System.identityHashCode(key));
"""  # noqa: E501


# A public interface with a private method.
# Source: https://github.com/mockito/mockito
#   commit 220c594adceebf92a0d06e2fb1e4398b25344d46
#   mockito-core/src/main/java/org/mockito/plugins/DoNotMockEnforcer.java
#   lines 1-99 (the whole file)
#   MIT License, Copyright (c) 2019 Mockito contributors
DO_NOT_MOCK_ENFORCER = rb"""/*
 * Copyright (c) 2019 Mockito contributors
 * This program is made available under the terms of the MIT License.
 */
package org.mockito.plugins;

import org.mockito.NotExtensible;
import org.mockito.mock.MockCreationSettings;

import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;

/**
 * Enforcer that is applied to every type in the type hierarchy of the class-to-be-mocked.
 */
public interface DoNotMockEnforcer extends DoNotMockEnforcerWithType {

    /**
     * Check whether this type is allowed to be mocked. Return {@code null} if the enforcer allows
     * this type to be mocked. Return a message if there is a reason this type can not be mocked.
     * <p>
     * Note that traversal of the type hierarchy is performed externally to this method.
     * Implementations of it should therefore not perform type traversal themselves.
     *
     * @param type The type to check
     * @return Optional message if this type can not be mocked, or {@code null} otherwise
     * @see #checkTypeForDoNotMockViolation(MockCreationSettings)
     */
    String checkTypeForDoNotMockViolation(Class<?> type);

    /**
     * Check whether this type is allowed to be mocked. Return {@code null} if the enforcer allows
     * this type to be mocked. Return a message if there is a reason this type can not be mocked.
     * <p>
     * The default implementation traverses the class hierarchy of the type to be mocked and
     * checks it against {@link #checkTypeForDoNotMockViolation(Class)}. If any types fails
     * the validation, the traversal is interrupted and the error message is returned.
     *
     * @param creationSettings The mock creation settings
     * @return Optional message if this type can not be mocked, or {@code null} otherwise
     * @since 5.9.0
     */
    @Override
    default String checkTypeForDoNotMockViolation(MockCreationSettings<?> creationSettings) {
        String warning = recursiveCheckDoNotMockAnnotationForType(creationSettings.getTypeToMock());
        if (warning != null) {
            return warning;
        }

        for (Class<?> aClass : creationSettings.getExtraInterfaces()) {
            warning = recursiveCheckDoNotMockAnnotationForType(aClass);
            if (warning != null) {
                return warning;
            }
        }

        return null;
    }

    private String recursiveCheckDoNotMockAnnotationForType(Class<?> type) {
        // Object and interfaces do not have a super class
        if (type == null) {
            return null;
        }

        if (Cache.MOCKABLE_TYPES.contains(type)) {
            return null;
        }

        String warning = checkTypeForDoNotMockViolation(type);
        if (warning != null) {
            return warning;
        }

        warning = recursiveCheckDoNotMockAnnotationForType(type.getSuperclass());
        if (warning != null) {
            return warning;
        }

        for (Class<?> aClass : type.getInterfaces()) {
            warning = recursiveCheckDoNotMockAnnotationForType(aClass);
            if (warning != null) {
                return warning;
            }
        }

        Cache.MOCKABLE_TYPES.add(type);
        return null;
    }

    /**
     * Static cache for types that are known to be mockable and
     * thus may be skipped while traversing the class hierarchy.
     */
    @NotExtensible
    class Cache {
        private static final Set<Class<?>> MOCKABLE_TYPES = ConcurrentHashMap.newKeySet();
    }
}
"""  # noqa: E501


# A public class with package-private static methods.
# Source: https://github.com/mockito/mockito
#   commit 220c594adceebf92a0d06e2fb1e4398b25344d46
#   mockito-core/src/main/java/org/mockito/internal/matchers/Equality.java
#   lines 1-46 (the whole file)
#   MIT License, Copyright (c) 2007 Mockito contributors
EQUALITY = rb"""/*
 * Copyright (c) 2007 Mockito contributors
 * This program is made available under the terms of the MIT License.
 */
package org.mockito.internal.matchers;

import java.lang.reflect.Array;

// stolen from hamcrest because I didn't want to have more dependency than Matcher class
public final class Equality {

    public static boolean areEqual(Object o1, Object o2) {
        if (o1 == o2) {
            return true;
        } else if (o1 == null || o2 == null) {
            return false;
        } else if (isArray(o1)) {
            return isArray(o2) && areArraysEqual(o1, o2);
        } else {
            return o1.equals(o2);
        }
    }

    static boolean areArraysEqual(Object o1, Object o2) {
        return areArrayLengthsEqual(o1, o2) && areArrayElementsEqual(o1, o2);
    }

    static boolean areArrayLengthsEqual(Object o1, Object o2) {
        return Array.getLength(o1) == Array.getLength(o2);
    }

    static boolean areArrayElementsEqual(Object o1, Object o2) {
        for (int i = 0; i < Array.getLength(o1); i++) {
            if (!areEqual(Array.get(o1, i), Array.get(o2, i))) {
                return false;
            }
        }
        return true;
    }

    static boolean isArray(Object o) {
        return o.getClass().isArray();
    }

    private Equality() {}
}
"""


def test_a_java_file_is_java() -> None:
    assert language_of("src/main/java/org/mockito/Mock.java") == "java"


def test_static_and_static_wildcard_imports() -> None:
    assert _imports(BYTECODE_GENERATOR) == {
        ("MethodDescription", 7, "net.bytebuddy.description.method"),
        ("ElementMatcher", 8, "net.bytebuddy.matcher"),
        ("*", 10, "net.bytebuddy.matcher.ElementMatchers"),
        ("named", 11, "net.bytebuddy.matcher.ElementMatchers"),
    }
    statements = {s.signature for s in _of(SymbolKind.IMPORT, BYTECODE_GENERATOR)}
    assert "import static net.bytebuddy.matcher.ElementMatchers.*;" in statements


def test_a_wildcard_import_is_a_star_import_of_the_package() -> None:
    assert ("*", 9, "java.util") in _imports(WEAK_IDENTITY_MAP)


def test_every_member_of_a_public_interface_is_exported() -> None:
    members = {
        ("mockClass", 15, "method"),
        ("mockClassConstruction", 17, "method"),
        ("mockClassStatic", 19, "method"),
        ("clearAllCaches", 21, "method"),
        ("isGroovyMethod", 23, "method"),
    }
    assert _definitions(BYTECODE_GENERATOR) == {
        ("BytecodeGenerator", 13, "interface"),
        *members,
    }
    assert _exports(BYTECODE_GENERATOR) == {
        ("BytecodeGenerator", 13),
        *((name, line) for name, line, _ in members),
    }


def test_an_annotated_declaration_is_found_on_its_names_line() -> None:
    """`@Override` sits on lines 19 and 32; the methods are named on 20 and 33, and
    the annotation stays in the signature, as a Python decorator does."""
    assert _definitions(COMPARE_TO) == {
        ("CompareTo", 11, "class"),
        ("CompareTo", 15, "constructor"),
        ("matches", 20, "method"),
        ("toString", 33, "method"),
        ("getName", 37, "method"),
        ("matchResult", 39, "method"),
    }
    assert _signature(COMPARE_TO, "matches", 20) == (
        "@Override\n    public final boolean matches(T actual)"
    )
    assert _signature(COMPARE_TO, "CompareTo", 11) == (
        "public abstract class CompareTo<T extends Comparable<T>>\n"
        "        implements ArgumentMatcher<T>, Serializable"
    )


def test_protected_members_are_exported_and_a_private_field_is_not() -> None:
    exports = _exports(COMPARE_TO)
    assert {("getName", 37), ("matchResult", 39), ("matches", 20)} <= exports
    assert "wanted" not in {name for name, _ in exports}


def test_calls_and_instance_creations_are_references() -> None:
    assert {
        ("getClass", 24),
        ("isInstance", 24),
        ("compareTo", 28),
        ("matchResult", 29),
        ("getName", 34),
    } <= _references(COMPARE_TO)
    assert {("HashMap", 23), ("ReferenceQueue", 24), ("poll", 29)} <= _references(
        WEAK_IDENTITY_MAP
    )


def test_an_interface_constant_is_exported_and_never_defined() -> None:
    assert ("DEFAULT_PRIORITY", 18) in _exports(VALUE_RENDERER)
    assert _definitions(VALUE_RENDERER) == {
        ("ValueRenderer", 17, "interface"),
        ("getPluginPriority", 28, "method"),
        ("print", 39, "method"),
    }
    assert _signature(VALUE_RENDERER, "ValueRenderer", 17) == (
        "@NullMarked\npublic interface ValueRenderer"
    )


def test_enum_constants_are_exported_at_their_own_lines() -> None:
    assert _definitions(STRICTNESS) == {("Strictness", 40, "enum")}
    assert _exports(STRICTNESS) == {
        ("Strictness", 40),
        ("LENIENT", 50),
        ("WARN", 62),
        ("STRICT_STUBS", 86),
    }


def test_nothing_in_a_package_private_class_is_exported() -> None:
    """Its `protected` field and the `public` method of the anonymous `Statement`
    inside it are no more visible outside the package than the class is."""
    assert _definitions(SESSION_STORE) == {
        ("JUnitSessionStore", 15, "class"),
        ("JUnitSessionStore", 21, "constructor"),
        ("createStatement", 26, "method"),
        ("evaluate", 29, "method"),
        ("evaluateSafely", 53, "method"),
        ("setStrictness", 64, "method"),
    }
    assert _exports(SESSION_STORE) == set()


def test_an_annotation_type_and_its_element() -> None:
    assert _definitions(MOCKITO_SETTINGS) == {
        ("MockitoSettings", 21, "annotation"),
        ("strictness", 27, "method"),
    }
    assert _exports(MOCKITO_SETTINGS) == {("MockitoSettings", 21), ("strictness", 27)}
    assert ("RUNTIME", 13, "java.lang.annotation.RetentionPolicy") in _imports(
        MOCKITO_SETTINGS
    )


def test_a_type_nested_in_a_public_interface_is_exported_with_its_members() -> None:
    definitions = _definitions(MOCKED_STATIC)
    assert {
        ("MockedStatic", 26, "interface"),
        ("Verification", 69, "interface"),
        ("apply", 76, "method"),
    } <= definitions
    assert _exports(MOCKED_STATIC) == {(name, line) for name, line, _ in definitions}
    assert ("times", 7, "org.mockito.Mockito") in _imports(MOCKED_STATIC)


def test_a_file_cut_mid_method_still_yields_what_parsed() -> None:
    """tree-sitter does not refuse a broken file: the class and both methods before
    the cut are found, and only the public ones are exported."""
    assert _definitions(WEAK_IDENTITY_MAP) == {
        ("WeakIdentityMap", 21, "class"),
        ("expungeStaleEntries", 27, "method"),
        ("get", 44, "method"),
    }
    assert _exports(WEAK_IDENTITY_MAP) == {("WeakIdentityMap", 21), ("get", 44)}


def test_a_private_method_of_a_public_interface_is_not_exported() -> None:
    assert ("recursiveCheckDoNotMockAnnotationForType", 60, "method") in (
        _definitions(DO_NOT_MOCK_ENFORCER)
    )
    exports = {name for name, _ in _exports(DO_NOT_MOCK_ENFORCER)}
    assert "recursiveCheckDoNotMockAnnotationForType" not in exports
    assert {"DoNotMockEnforcer", "checkTypeForDoNotMockViolation"} <= exports


def test_package_private_methods_of_a_public_class_are_not_exported() -> None:
    assert _exports(EQUALITY) == {("Equality", 10), ("areEqual", 12)}
    assert {
        ("areArraysEqual", 24, "method"),
        ("areArrayLengthsEqual", 28, "method"),
        ("areArrayElementsEqual", 32, "method"),
        ("isArray", 41, "method"),
    } <= _definitions(EQUALITY)
