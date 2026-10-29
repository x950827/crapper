from crapper.languages.kotlin import functions_in_source

SCORE = """
class Sample {
    fun score(a: Boolean, b: Boolean, values: List<Int>, text: String?): Int {
        for (value in values) {
        }
        while (a) {
        }
        do {
        } while (b)
        if (a && b || values.isEmpty()) {
        }
        val length = text?.length ?: 0
        return try {
            if (a) 1 else 0
        } catch (ex: RuntimeException) {
            2
        }
    }
}
"""

WHEN = """
class Sample {
    fun switched(value: Int): Int {
        return when (value) {
            1 -> if (value > 0) 1 else 0
            2, 3 -> 2
            else -> 3
        }
    }

    fun guarded(a: Boolean): Int = when {
        a -> 1
        else -> 0
    }
}
"""

NESTED = """
class Sample {
    fun outer(values: List<Int>): Int {
        fun local(x: Int): Int {
            if (x > 0) {
                return 1
            }
            return 0
        }
        values.forEach { if (it > 1) println(it) }
        val runnable = object : Runnable {
            override fun run() {
                if (values.isEmpty()) {
                }
            }
        }
        return local(1)
    }
}
"""


def test_counts_the_same_decisions_as_the_java_reader():
    functions = functions_in_source(SCORE, "Sample.kt")
    # 1 + for + while + do + if + && + || + ?: + try's if + catch
    assert [(f.name, f.complexity) for f in functions] == [("score", 10)]


def test_each_when_entry_is_a_decision_like_a_java_switch_label():
    functions = functions_in_source(WHEN, "Sample.kt")
    assert [(f.name, f.complexity) for f in functions] == [
        ("switched", 5),
        ("guarded", 3),
    ]


def test_lambdas_and_local_functions_stay_inside_anonymous_objects_do_not():
    functions = functions_in_source(NESTED, "Sample.kt")
    # 1 + local's if + the lambda's if; the anonymous object's if is not counted
    assert [(f.name, f.complexity) for f in functions] == [("outer", 3)]


def test_names_types_for_uml_viewer_and_jacoco():
    source = """
package demo.billing

class Invoice {
    constructor(total: Int) {
        if (total > 0) {
        }
    }

    init {
        if (true) {
        }
    }

    val label: String
        get() = if (paid) "paid" else "open"

    fun pay(amount: Int): Boolean {
        return amount > 0 && !paid
    }

    abstract fun audit(): Int

    inner class Line {
        fun total(): Int = 1
    }

    companion object {
        fun empty(): Invoice = Invoice(0)
    }
}

object Registry {
    fun lookup(id: String?): Int = id?.length ?: 0
}
"""
    functions = functions_in_source(source, "src/demo/billing/Invoice.kt")
    assert [(f.namespace, f.name, f.complexity, f.jacoco_class) for f in functions] == [
        ("demo.billing.Invoice", "pay", 2, "demo.billing.Invoice"),
        ("demo.billing.Invoice.Line", "total", 1, "demo.billing.Invoice$Line"),
        ("demo.billing.Invoice.Companion", "empty", 1, "demo.billing.Invoice$Companion"),
        ("demo.billing.Registry", "lookup", 2, "demo.billing.Registry"),
    ]
    assert all(f.language == "kotlin" for f in functions)


def test_top_level_functions_belong_to_the_file_facade():
    source = """
package demo.util

fun String.initials(): String = if (isEmpty()) "" else take(1)

fun clamp(x: Int): Int {
    return if (x < 0) 0 else x
}
"""
    functions = functions_in_source(source, "src/demo/util/strings.kt")
    assert [(f.namespace, f.name, f.jacoco_class) for f in functions] == [
        ("demo.util.StringsKt", "initials", "demo.util.StringsKt"),
        ("demo.util.StringsKt", "clamp", "demo.util.StringsKt"),
    ]


def test_jvm_name_renames_the_facade():
    source = """
@file:JvmName("Money")

package demo.util

fun round(x: Double): Long = x.toLong()
"""
    functions = functions_in_source(source, "src/demo/util/MoneyUtils.kt")
    assert [(f.namespace, f.jacoco_class) for f in functions] == [
        ("demo.util.Money", "demo.util.Money")
    ]


def test_keywords_in_comments_and_strings_are_not_decisions():
    source = """
class Sample {
    fun stable(): Int {
        val text = "if && || ?: when catch"
        // if && || ?: when catch
        /* if && || ?: when catch */
        return 1
    }
}
"""
    functions = functions_in_source(source, "Sample.kt")
    assert [(f.name, f.complexity) for f in functions] == [("stable", 1)]


def test_backticked_names_lose_their_backticks_like_the_class_file():
    source = """
package demo.`billing`

class Spec {
    fun `does a thing`(): Int = 1
}
"""
    functions = functions_in_source(source, "Spec.kt")
    assert [(f.namespace, f.name) for f in functions] == [("demo.billing.Spec", "does a thing")]


def test_facade_names_follow_kotlinc_for_awkward_file_names():
    source = "package p\n\nfun f(): Int = 1\n"
    facades = [
        functions_in_source(source, name)[0].jacoco_class
        for name in ("my-utils.kt", "1st.kt", "string.utils.kt")
    ]
    assert facades == ["p.My_utilsKt", "p._1stKt", "p.String_utilsKt"]


def test_package_and_file_annotations_come_from_the_header_not_from_comments():
    source = """
// see @file:JvmName("Nope")
/*
 package wrong.pkg
*/
@file:[Suppress("unused") kotlin.jvm.JvmName("Money")]

package demo.util

fun round(x: Double): Long = x.toLong()
"""
    functions = functions_in_source(source, "MoneyUtils.kt")
    assert [(f.namespace, f.jacoco_class) for f in functions] == [
        ("demo.util.Money", "demo.util.Money")
    ]


def test_multifile_facade_bodies_live_in_their_part_class():
    source = """
@file:JvmName("Money")
@file:JvmMultifileClass

package demo.util

fun round(x: Double): Long = x.toLong()
"""
    functions = functions_in_source(source, "MoneyUtils.kt")
    assert [(f.namespace, f.jacoco_class) for f in functions] == [
        ("demo.util.Money", "demo.util.Money__MoneyUtilsKt")
    ]


def test_enum_entry_bodies_are_their_own_class():
    source = """
package p

enum class Op {
    PLUS {
        override fun apply(a: Int, b: Int) = if (a > 0) a + b else b
    },
    MINUS {
        override fun apply(a: Int, b: Int) = a - b
    };

    abstract fun apply(a: Int, b: Int): Int

    fun describe(): String = name
}
"""
    functions = functions_in_source(source, "Op.kt")
    assert [(f.namespace, f.name, f.complexity, f.jacoco_class) for f in functions] == [
        ("p.Op.PLUS", "apply", 2, "p.Op$PLUS"),
        ("p.Op.MINUS", "apply", 1, "p.Op$MINUS"),
        ("p.Op", "describe", 1, "p.Op"),
    ]
