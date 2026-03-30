"""Tests for fixture_graph.core module."""

from fixture_graph.core import (
    Config,
    FixtureGraph,
    FixtureSetup,
    ParsedTestCase,
    Pattern,
    PatternKey,
    SetupPlan,
    _ancestors,  # type: ignore[attr-defined]
    _terminal_fixtures,  # type: ignore[attr-defined]
    is_parametrized_fixture,
    normalize_fixture_name,
    parse_entry,
    parse_fixture_list,
)


def test_fixture_setup_str_no_dependencies() -> None:
    """Test string representation without dependencies."""
    fixture = FixtureSetup(name="db", dependencies=())
    assert str(fixture) == "db"


def test_fixture_setup_str_with_dependencies() -> None:
    """Test string representation with dependencies."""
    fixture = FixtureSetup(name="db", dependencies=("config", "tmpdir"))
    assert str(fixture) == "db <- config, tmpdir"


def test_parsed_test_case_name_extraction() -> None:
    """Test extracting test name from node ID."""
    test = ParsedTestCase(
        node_id="tests/test_foo.py::test_bar",
        test_file="tests/test_foo.py",
        fixtures=(),
    )
    assert test.name == "test_bar"


def test_parsed_test_case_name_with_class() -> None:
    """Test extracting test name from parametrized test."""
    test = ParsedTestCase(
        node_id="tests/test_foo.py::TestClass::test_method",
        test_file="tests/test_foo.py",
        fixtures=(),
    )
    assert test.name == "TestClass::test_method"


def test_parsed_test_case_str_no_fixtures() -> None:
    """Test string representation without fixtures."""
    test = ParsedTestCase(
        node_id="tests/test_foo.py::test_bar",
        test_file="tests/test_foo.py",
        fixtures=(),
    )
    assert str(test) == "tests/test_foo.py::test_bar"


def test_parsed_test_case_str_with_fixtures() -> None:
    """Test string representation with fixtures."""
    test = ParsedTestCase(
        node_id="tests/test_foo.py::test_bar",
        test_file="tests/test_foo.py",
        fixtures=("db", "cache"),
    )
    assert str(test) == "tests/test_foo.py::test_bar (db, cache)"


def test_parsed_test_case_pattern_key() -> None:
    """Test pattern_key computation."""
    fixture_graph = FixtureGraph(
        dependencies_by_fixture={"db": frozenset()},
        config=Config(exclude_fixtures=frozenset()),
    )
    test = ParsedTestCase(
        node_id="tests/test_foo.py::test_bar",
        test_file="tests/test_foo.py",
        fixtures=("db",),
    )
    cache: dict[str, frozenset[str]] = {}
    key = test.pattern_key(fixture_graph, cache)
    assert key.test_file == "tests/test_foo.py"
    assert "db" in key.terminal_fixtures


def test_normalize_fixture_name() -> None:
    """Test fixture name normalization."""
    assert normalize_fixture_name("db[postgresql]") == "db"
    assert normalize_fixture_name("simple_fixture") == "simple_fixture"


def test_parse_fixture_list() -> None:
    """Test parsing comma-separated fixture lists."""
    result = parse_fixture_list("db[postgres], cache, tmp_path")
    assert result == ("db", "cache", "tmp_path")


def test_parse_fixture_list_empty() -> None:
    """Test parsing empty fixture list."""
    assert parse_fixture_list("") == ()


def test_parse_entry_fixture_setup() -> None:
    """Test parsing fixture setup line."""
    line = "SETUP    M db (fixtures used: config, cache)"
    entry = parse_entry(line)
    assert isinstance(entry, FixtureSetup)
    assert entry.name == "db"
    assert entry.dependencies == ("config", "cache")


def test_parse_entry_test_case() -> None:
    """Test parsing test case line."""
    line = "tests/test_api.py::test_endpoint (fixtures used: db, client)"
    entry = parse_entry(line)
    assert isinstance(entry, ParsedTestCase)
    assert entry.node_id == "tests/test_api.py::test_endpoint"
    assert entry.test_file == "tests/test_api.py"
    assert entry.fixtures == ("db", "client")


def test_parse_entry_invalid_line() -> None:
    """Test parsing invalid line returns None."""
    assert parse_entry("some random text") is None
    assert parse_entry("  INVALID LINE") is None


def test_test_pattern_count() -> None:
    """Test count property."""
    expected_count = 3
    pattern = Pattern(
        key=PatternKey(test_file="tests/test_a.py", terminal_fixtures=()),
        test_names=("test_one", "test_two", "test_three"),
    )
    assert pattern.count == expected_count


def test_test_pattern_label_lines() -> None:
    """Test label_lines method."""
    pattern = Pattern(
        key=PatternKey(test_file="tests/test_a.py", terminal_fixtures=("db", "cache")),
        test_names=("test_one", "test_two"),
    )
    lines = pattern.label_lines()
    assert lines[0] == "test_a.py"
    assert lines[1] == "2 test(s)"
    assert "test_one" in lines
    assert "test_two" in lines
    assert "db, cache" in lines


def test_test_pattern_render_dot() -> None:
    """Test render_dot produces valid DOT lines."""
    fixture_graph = FixtureGraph(
        dependencies_by_fixture={"db": frozenset()},
        config=Config(exclude_fixtures=frozenset()),
    )
    pattern = Pattern(
        key=PatternKey(
            test_file="tests/test_a.py",
            terminal_fixtures=("db",),
            all_fixtures=("db",),
        ),
        test_names=("test_one",),
    )
    lines = pattern.render_dot(1, fixture_graph)
    assert any("shape=note" in line for line in lines)
    assert any("[style=dashed" in line for line in lines)


def test_test_pattern_render_dot_no_fixture_in_graph() -> None:
    """Test render_dot skips fixture not in graph."""
    fixture_graph = FixtureGraph(
        dependencies_by_fixture={},
        config=Config(exclude_fixtures=frozenset()),
    )
    pattern = Pattern(
        key=PatternKey(
            test_file="tests/test_a.py",
            terminal_fixtures=("unknown",),
            all_fixtures=("unknown",),
        ),
        test_names=("test_one",),
    )
    lines = pattern.render_dot(1, fixture_graph)
    # Should still have the node, but no edge
    assert any("shape=note" in line for line in lines)
    # No dashed edge since fixture not in graph
    assert not any("[style=dashed" in line for line in lines)


def test_test_pattern_key_fixture_summary_with_fixtures() -> None:
    """Test fixture_summary with fixtures."""
    key = PatternKey(test_file="tests/test_a.py", terminal_fixtures=("db", "cache"))
    assert key.fixture_summary() == "db, cache"


def test_test_pattern_key_fixture_summary_empty() -> None:
    """Test fixture_summary with no fixtures."""
    key = PatternKey(test_file="tests/test_a.py", terminal_fixtures=())
    assert key.fixture_summary() == "no explicit non-builtin fixture"


def test_fixture_graph_names_sorted() -> None:
    """Test that fixture names are returned in sorted order."""
    graph = FixtureGraph(
        dependencies_by_fixture={
            "zebra": frozenset(),
            "apple": frozenset(),
            "banana": frozenset(),
        },
        config=Config(exclude_fixtures=frozenset()),
    )
    assert graph.names == ("apple", "banana", "zebra")


def test_fixture_graph_dependencies_missing_fixture() -> None:
    """Test dependencies returns empty frozenset for missing fixture."""
    graph = FixtureGraph(
        dependencies_by_fixture={"db": frozenset(["config"])},
        config=Config(exclude_fixtures=frozenset()),
    )
    assert graph.dependencies("nonexistent") == frozenset()


def test_fixture_graph_dependencies_existing_fixture() -> None:
    """Test dependencies returns correct deps for existing fixture."""
    graph = FixtureGraph(
        dependencies_by_fixture={"db": frozenset(["config", "cache"])},
        config=Config(exclude_fixtures=frozenset()),
    )
    assert graph.dependencies("db") == frozenset(["config", "cache"])


def test_fixture_graph_render_fixture_node_builtin() -> None:
    """Test render_fixture_node for built-in fixture."""
    graph = FixtureGraph(
        dependencies_by_fixture={"request": frozenset()},
        config=Config(exclude_fixtures=frozenset()),
    )
    node = graph.render_fixture_node("request")
    assert 'fillcolor="#e5e7eb"' in node  # gray for builtin


def test_fixture_graph_render_fixture_node_excluded() -> None:
    """Test render_fixture_node for excluded fixture."""
    graph = FixtureGraph(
        dependencies_by_fixture={"my_fixture": frozenset()},
        config=Config(exclude_fixtures=frozenset({"my_fixture"})),
    )
    node = graph.render_fixture_node("my_fixture")
    assert 'fillcolor="#fde68a"' in node  # yellow for excluded


def test_fixture_graph_render_fixture_node_custom() -> None:
    """Test render_fixture_node for custom fixture."""
    graph = FixtureGraph(
        dependencies_by_fixture={"my_fixture": frozenset()},
        config=Config(exclude_fixtures=frozenset()),
    )
    node = graph.render_fixture_node("my_fixture")
    assert 'fillcolor="#bfdbfe"' in node  # blue for custom


def test_fixture_graph_render_cluster() -> None:
    """Test render_cluster produces valid DOT lines."""
    graph = FixtureGraph(
        dependencies_by_fixture={"db": frozenset(), "cache": frozenset()},
        config=Config(exclude_fixtures=frozenset()),
    )
    cluster = graph.render_cluster()
    assert any("subgraph cluster_fixtures" in line for line in cluster)
    assert any('label="Fixtures"' in line for line in cluster)
    assert cluster[-1] == "  }"


def test_fixture_graph_render_dependency_edges() -> None:
    """Test render_dependency_edges produces edges."""
    graph = FixtureGraph(
        dependencies_by_fixture={
            "db": frozenset(["config"]),
            "config": frozenset(),
        },
        config=Config(exclude_fixtures=frozenset()),
    )
    edges = graph.render_dependency_edges()
    assert len(edges) == 1
    assert "fixture_config" in edges[0]
    assert "fixture_db" in edges[0]
    assert "->" in edges[0]


def test_fixture_graph_render_dependency_edges_skip_external() -> None:
    """Test render_dependency_edges skips external dependencies."""
    graph = FixtureGraph(
        dependencies_by_fixture={
            "db": frozenset(["external_dep"]),
        },
        config=Config(exclude_fixtures=frozenset()),
    )
    edges = graph.render_dependency_edges()
    assert len(edges) == 0  # external_dep not in graph, so skipped


def test_setup_plan_parse_simple_plan() -> None:
    """Test parsing a simple setup plan."""
    text = """\
SETUP    M db (fixtures used: config)
SETUP    M cache (fixtures used: )
tests/test_app.py::test_endpoint (fixtures used: db, cache)
"""
    plan = SetupPlan.parse(text, Config(exclude_fixtures=frozenset()))
    expected_fixture_count = 2
    expected_test_count = 1
    assert len(plan.fixtures.names) == expected_fixture_count
    assert len(plan.tests) == expected_test_count
    assert plan.tests[0].node_id == "tests/test_app.py::test_endpoint"


def test_setup_plan_filter_exclude_fixtures() -> None:
    """Test that excluded fixtures are filtered out."""
    text = """\
SETUP    M db (fixtures used: tmp_path_factory)
tests/test_app.py::test_endpoint (fixtures used: db, tmp_path_factory)
"""
    plan = SetupPlan.parse(
        text, Config(exclude_fixtures=frozenset({"tmp_path_factory"}))
    )
    assert "tmp_path_factory" not in plan.fixtures.names
    assert "db" in plan.fixtures.names


def test_setup_plan_render_dot_produces_valid_format() -> None:
    """Test that render_dot produces valid DOT graph."""
    text = """\
SETUP    M db (fixtures used: )
tests/test_app.py::test_endpoint (fixtures used: db)
"""
    plan = SetupPlan.parse(text, Config(exclude_fixtures=frozenset()))
    dot = plan.render_dot()
    assert "digraph pytest_setup_plan" in dot
    assert "cluster_fixtures" in dot
    assert "cluster_test" in dot
    assert "}" in dot


def test_setup_plan_parse_with_dependency_filtering() -> None:
    """Test that dependencies are filtered by exclude_fixtures."""
    text = """\
SETUP    M db (fixtures used: config, tmp_path_factory)
SETUP    M config (fixtures used: )
"""
    plan = SetupPlan.parse(
        text, Config(exclude_fixtures=frozenset({"tmp_path_factory"}))
    )
    # db should only have "config" as dep, not tmp_path_factory
    assert plan.fixtures.dependencies("db") == frozenset(["config"])


def test_setup_plan_group_test_patterns_empty() -> None:
    """Test group_test_patterns with no tests."""
    plan = SetupPlan(
        fixtures=FixtureGraph(
            dependencies_by_fixture={},
            config=Config(exclude_fixtures=frozenset()),
        ),
        tests=(),
        config=Config(exclude_fixtures=frozenset()),
    )
    grouped = plan.group_test_patterns()
    assert grouped == {}


def test_setup_plan_group_test_patterns_single_file() -> None:
    """Test group_test_patterns groups tests by file."""
    expected_count = 2
    fixture_graph = FixtureGraph(
        dependencies_by_fixture={"db": frozenset()},
        config=Config(exclude_fixtures=frozenset()),
    )
    tests = (
        ParsedTestCase(
            node_id="tests/test_a.py::test_one",
            test_file="tests/test_a.py",
            fixtures=("db",),
        ),
        ParsedTestCase(
            node_id="tests/test_a.py::test_two",
            test_file="tests/test_a.py",
            fixtures=("db",),
        ),
    )
    plan = SetupPlan(
        fixtures=fixture_graph,
        tests=tests,
        config=Config(exclude_fixtures=frozenset()),
    )
    grouped = plan.group_test_patterns()
    assert "tests/test_a.py" in grouped
    # Both tests should be grouped together since they use same fixtures
    assert len(grouped["tests/test_a.py"]) == 1
    assert grouped["tests/test_a.py"][0].count == expected_count


def test_setup_plan_render_test_cluster() -> None:
    """Test render_test_cluster produces valid DOT lines."""
    fixture_graph = FixtureGraph(
        dependencies_by_fixture={"db": frozenset()},
        config=Config(exclude_fixtures=frozenset()),
    )
    pattern = Pattern(
        key=PatternKey(test_file="tests/test_a.py", terminal_fixtures=("db",)),
        test_names=("test_one", "test_two"),
    )
    plan = SetupPlan(
        fixtures=fixture_graph,
        tests=(),
        config=Config(exclude_fixtures=frozenset()),
    )
    cluster = plan.render_test_cluster("tests/test_a.py", (pattern,))
    assert any("subgraph cluster" in line for line in cluster)
    assert cluster[-1] == "  }"


def test_setup_plan_parse_excludes_fixtures_from_entries() -> None:
    """Test that excluded fixtures are removed from the graph entirely."""
    text = """\
SETUP    M excluded_fixture (fixtures used: )
SETUP    M db (fixtures used: excluded_fixture, config)
SETUP    M config (fixtures used: )
tests/test_app.py::test_endpoint (fixtures used: db, excluded_fixture)
"""
    plan = SetupPlan.parse(
        text, Config(exclude_fixtures=frozenset({"excluded_fixture"}))
    )
    # excluded_fixture should not be in graph
    assert "excluded_fixture" not in plan.fixtures.names
    # db's dependencies should not include excluded_fixture
    assert plan.fixtures.dependencies("db") == frozenset(["config"])


def test_ancestors_with_transitive_dependencies() -> None:
    """Test ancestor computation with transitive dependencies."""
    fixture_graph = FixtureGraph(
        dependencies_by_fixture={
            "a": frozenset(["b"]),
            "b": frozenset(["c"]),
            "c": frozenset(),
        },
        config=Config(exclude_fixtures=frozenset()),
    )
    cache: dict[str, frozenset[str]] = {}
    # a depends on b and transitively on c
    result = _ancestors("a", fixture_graph, cache)
    assert result == frozenset(["b", "c"])
    # Check that cache is populated
    assert "a" in cache
    assert "b" in cache
    assert "c" in cache


def test_ancestors_with_cache_reuse() -> None:
    """Test that ancestor cache is reused for multiple calls."""
    fixture_graph = FixtureGraph(
        dependencies_by_fixture={
            "a": frozenset(["b"]),
            "b": frozenset(["c"]),
            "c": frozenset(),
            "d": frozenset(["b"]),
        },
        config=Config(exclude_fixtures=frozenset()),
    )
    cache: dict[str, frozenset[str]] = {}
    # Compute ancestors for 'a' which includes 'b'
    _ancestors("a", fixture_graph, cache)
    initial_cache_size = len(cache)
    # Compute ancestors for 'd' which also depends on 'b'
    # Should reuse cached result for 'b'
    _ancestors("d", fixture_graph, cache)
    # Cache should have one additional entry for 'd' only
    assert len(cache) == initial_cache_size + 1


def test_terminal_fixtures_filters_builtin_and_excluded() -> None:
    """Test terminal_fixtures filters builtin and excluded fixtures."""
    fixture_graph = FixtureGraph(
        dependencies_by_fixture={
            "db": frozenset(),
            "request": frozenset(),
            "excluded": frozenset(),
        },
        config=Config(exclude_fixtures=frozenset({"excluded"})),
    )
    cache: dict[str, frozenset[str]] = {}
    # Pass request, excluded, and db
    result = _terminal_fixtures(("request", "excluded", "db"), fixture_graph, cache)
    # Only db should remain (request is builtin, excluded is excluded)
    assert result == ("db",)


def test_terminal_fixtures_removes_implied_fixtures() -> None:
    """Test terminal_fixtures removes fixtures implied by others."""
    fixture_graph = FixtureGraph(
        dependencies_by_fixture={
            "db": frozenset(["config"]),
            "config": frozenset(),
        },
        config=Config(exclude_fixtures=frozenset()),
    )
    cache: dict[str, frozenset[str]] = {}
    # Pass both db and config - config is implied by db
    result = _terminal_fixtures(("db", "config"), fixture_graph, cache)
    # Only db should remain (config is transitively included)
    assert result == ("db",)


def test_is_parametrized_fixture() -> None:
    """Test detection of parametrized fixtures."""

    assert is_parametrized_fixture("content['value']")
    assert is_parametrized_fixture("content[0]")
    assert not is_parametrized_fixture("regular_fixture")
    assert not is_parametrized_fixture("fixture_with_brackets[")


def test_parse_entry_parametrized() -> None:
    """Test parsing parametrized fixture entries."""
    line = "SETUP    F content['value']"
    entry = parse_entry(line)
    assert isinstance(entry, FixtureSetup)
    assert entry.name == "content"
    assert entry.is_parametrized is True


def test_parse_entry_regular_fixture() -> None:
    """Test parsing regular fixture entries."""
    line = "SETUP    F db (fixtures used: config)"
    entry = parse_entry(line)
    assert isinstance(entry, FixtureSetup)
    assert entry.name == "db"
    assert entry.is_parametrized is False


def test_parametrize_display_hide() -> None:
    """Test hiding parametrized fixtures."""
    text = """\
SETUP    F content['value']
SETUP    F db (fixtures used: )
tests/test_app.py::test_endpoint (fixtures used: content, db)
"""
    config = Config(exclude_fixtures=frozenset(), parametrize_display="hide")
    plan = SetupPlan.parse(text, config)
    # content should be hidden, only db should be in graph
    assert "db" in plan.fixtures.names
    assert "content" not in plan.fixtures.names


def test_parametrize_display_show() -> None:
    """Test showing parametrized fixtures without highlighting."""
    text = """\
SETUP    F content['value']
SETUP    F db (fixtures used: )
tests/test_app.py::test_endpoint (fixtures used: content, db)
"""
    config = Config(exclude_fixtures=frozenset(), parametrize_display="show")
    plan = SetupPlan.parse(text, config)
    # Both should be in graph
    assert "db" in plan.fixtures.names
    assert "content" in plan.fixtures.names


def test_parametrize_display_highlight() -> None:
    """Test highlighting parametrized fixtures."""
    text = """\
SETUP    F content['value']
SETUP    F db (fixtures used: )
tests/test_app.py::test_endpoint (fixtures used: content, db)
"""
    config = Config(exclude_fixtures=frozenset(), parametrize_display="highlight")
    plan = SetupPlan.parse(text, config)
    # Both should be in graph
    assert "db" in plan.fixtures.names
    assert "content" in plan.fixtures.names
    # content should be marked as parametrized
    assert "content" in plan.fixtures.parametrized_fixtures
    assert "db" not in plan.fixtures.parametrized_fixtures


def test_fixture_graph_parametrized_color() -> None:
    """Test that parametrized fixtures get green color when highlighted."""
    graph = FixtureGraph(
        dependencies_by_fixture={"content": frozenset(), "db": frozenset()},
        config=Config(exclude_fixtures=frozenset(), parametrize_display="highlight"),
        parametrized_fixtures=frozenset(["content"]),
    )
    content_attrs = graph._dot_attributes("content")  # type: ignore[attr-defined]
    db_attrs = graph._dot_attributes("db")  # type: ignore[attr-defined]
    # content should be green, db should be blue
    assert 'fillcolor="#bbf7d0"' in content_attrs  # green
    assert 'fillcolor="#bfdbfe"' in db_attrs  # blue


def test_fixture_graph_parametrized_no_highlight() -> None:
    """Test that parametrized fixtures get normal color when not highlighted."""
    graph = FixtureGraph(
        dependencies_by_fixture={"content": frozenset(), "db": frozenset()},
        config=Config(exclude_fixtures=frozenset(), parametrize_display="show"),
        parametrized_fixtures=frozenset(["content"]),
    )
    content_attrs = graph._dot_attributes("content")  # type: ignore[attr-defined]
    db_attrs = graph._dot_attributes("db")  # type: ignore[attr-defined]
    # Both should be blue (normal color)
    assert 'fillcolor="#bfdbfe"' in content_attrs
    assert 'fillcolor="#bfdbfe"' in db_attrs
