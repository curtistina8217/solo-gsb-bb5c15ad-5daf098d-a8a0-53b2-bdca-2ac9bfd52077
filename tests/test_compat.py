"""兼容性引擎测试。"""
import pytest

from app import compat


def analyze(old, new, samples=None):
    return compat.analyze(old, new, samples)


def codes(report, direction):
    return [i["code"] for i in report["issues"] if i["direction"] == direction]


class TestBasicCompatibility:
    def test_add_optional_field_is_compatible_both_ways(self):
        old = {"type": "object", "properties": {"a": {"type": "string"}}}
        new = {"type": "object", "properties": {"a": {"type": "string"},
                                               "b": {"type": "integer"}}}
        report = analyze(old, new)
        assert report["backward_compatible"]
        assert report["forward_compatible"]

    def test_add_required_field_breaks_backward_only(self):
        old = {"type": "object", "properties": {"a": {"type": "string"}}}
        new = {"type": "object", "properties": {"a": {"type": "string"},
                                                "b": {"type": "string"}},
               "required": ["b"]}
        report = analyze(old, new)
        assert not report["backward_compatible"]
        assert report["forward_compatible"]
        assert "required_added" in codes(report, "backward")

    def test_remove_required_field_breaks_forward_only(self):
        old = {"type": "object", "properties": {"a": {"type": "string"}},
               "required": ["a"]}
        new = {"type": "object", "properties": {"a": {"type": "string"}}}
        report = analyze(old, new)
        assert report["backward_compatible"]
        assert not report["forward_compatible"]


class TestType:
    def test_type_change_breaks_both(self):
        report = analyze({"type": "string"}, {"type": "integer"})
        assert not report["backward_compatible"]
        assert not report["forward_compatible"]
        assert codes(report, "backward") == ["type_removed"]
        assert codes(report, "forward") == ["type_removed"]

    def test_integer_to_number_backward_compatible(self):
        # number 是 integer 的超集
        report = analyze({"type": "integer"}, {"type": "number"})
        assert report["backward_compatible"]


class TestEnum:
    def test_enum_narrowed(self):
        report = analyze({"enum": ["a", "b", "c"]}, {"enum": ["a", "b"]})
        assert not report["backward_compatible"]
        assert report["forward_compatible"]
        issue = [i for i in report["issues"] if i["code"] == "enum_value_removed"][0]
        assert issue["counterexample"] == "c"

    def test_enum_widened_breaks_forward(self):
        report = analyze({"enum": ["a", "b"]}, {"enum": ["a", "b", "c"]})
        assert report["backward_compatible"]
        assert not report["forward_compatible"]


class TestConst:
    def test_const_added(self):
        report = analyze({"type": "string"}, {"const": "v1"})
        assert not report["backward_compatible"]
        issue = [i for i in report["issues"] if i["code"] == "const_added"][0]
        assert issue["counterexample"] is not None  # 空字符串也是合法反例

    def test_const_changed_breaks_both(self):
        report = analyze({"const": "a"}, {"const": "b"})
        assert not report["backward_compatible"]
        assert not report["forward_compatible"]


class TestArray:
    def test_homogeneous_item_type(self):
        report = analyze({"type": "array", "items": {"type": "string"}},
                         {"type": "array", "items": {"type": "integer"}})
        assert not report["backward_compatible"]
        assert not report["forward_compatible"]
        ce = [i for i in report["issues"] if i["direction"] == "backward"][0]["counterexample"]
        assert ce == [""]

    def test_min_items_increased(self):
        report = analyze({"type": "array"}, {"type": "array", "minItems": 2})
        assert not report["backward_compatible"]
        ce = [i for i in report["issues"]][0]["counterexample"]
        assert ce == []

    def test_max_items_decreased(self):
        report = analyze({"type": "array", "maxItems": 5},
                         {"type": "array", "maxItems": 2})
        assert not report["backward_compatible"]

    def test_unique_items_added(self):
        report = analyze({"type": "array", "items": {"type": "string"}},
                         {"type": "array", "items": {"type": "string"},
                          "uniqueItems": True})
        assert not report["backward_compatible"]

    def test_legacy_tuple_additional_items_false(self):
        old = {"type": "array", "items": [{"type": "string"}],
               "additionalItems": True}
        new = {"type": "array", "items": [{"type": "string"}],
               "additionalItems": False}
        report = analyze(old, new)
        assert not report["backward_compatible"]
        issue = report["issues"][0]
        assert issue["path"] == "#/items"
        # 反例必须是含一个超出前缀元素的数组
        assert len(issue["counterexample"]) == 2

    def test_legacy_tuple_unchanged_prefix_is_compatible(self):
        old = {"type": "array",
               "items": [{"type": "string"}, {"type": "integer"}]}
        new = {"type": "array",
               "items": [{"type": "string"}, {"type": "integer"}],
               "additionalItems": False}
        report = analyze(old, new)
        assert report["backward_compatible"]

    def test_2020_tuple_path_uses_prefix_items(self):
        old = {"type": "array", "prefixItems": [{"type": "string"}], "items": True}
        new = {"type": "array", "prefixItems": [{"type": "integer"}], "items": True}
        report = analyze(old, new)
        assert report["issues"][0]["path"] == "#/prefixItems/0"


class TestObject:
    def test_additional_properties_false(self):
        old = {"type": "object", "properties": {"a": {"type": "string"}}}
        new = {"type": "object", "properties": {"a": {"type": "string"}},
               "additionalProperties": False}
        report = analyze(old, new)
        assert not report["backward_compatible"]

    def test_removed_property_with_ap_false(self):
        old = {"type": "object", "properties": {"a": {}, "b": {}}}
        new = {"type": "object", "properties": {"a": {}},
               "additionalProperties": False}
        report = analyze(old, new)
        assert not report["backward_compatible"]
        assert any(i["code"] == "property_no_longer_allowed" for i in report["issues"])

    def test_min_properties(self):
        report = analyze({"type": "object", "minProperties": 1},
                         {"type": "object", "minProperties": 3})
        assert not report["backward_compatible"]


class TestNumbers:
    def test_minimum_raised(self):
        report = analyze({"type": "integer"}, {"type": "integer", "minimum": 0})
        assert not report["backward_compatible"]
        assert report["issues"][0]["counterexample"] == -1

    def test_draft4_exclusive_minimum(self):
        old = {"type": "number", "minimum": 0}
        new = {"type": "number", "minimum": 0, "exclusiveMinimum": True}
        report = analyze(old, new)
        assert not report["backward_compatible"]
        assert report["issues"][0]["counterexample"] == 0

    def test_maximum_lowered(self):
        report = analyze({"type": "number", "maximum": 100},
                         {"type": "number", "maximum": 50})
        assert not report["backward_compatible"]


class TestComposition:
    def test_anyof_added(self):
        old = {"type": "object", "properties": {"x": {}}}
        new = {"type": "object", "properties": {"x": {}},
               "anyOf": [{"required": ["x"]}, {"required": ["y"]}]}
        report = analyze(old, new)
        # {} 旧版合法但不满足 anyOf
        assert not report["backward_compatible"]

    def test_not_added(self):
        report = analyze({"type": "string"},
                         {"type": "string", "not": {"enum": ["x"]}})
        assert not report["backward_compatible"]


class TestRef:
    def test_internal_ref_type_change(self):
        old = {"$ref": "#/$defs/id", "$defs": {"id": {"type": "integer"}}}
        new = {"$ref": "#/$defs/id", "$defs": {"id": {"type": "string"}}}
        report = analyze(old, new)
        assert not report["backward_compatible"]
        assert not report["forward_compatible"]


class TestCounterexamples:
    """每个 error 若附了反例，反例必须真实满足旧版、违反新版。"""

    @pytest.mark.parametrize("old,new", [
        ({"type": "object", "properties": {"a": {"type": "string"}}},
         {"type": "object", "properties": {"a": {"type": "string"}},
          "required": ["a"]}),
        ({"type": "string", "enum": ["a", "b"]}, {"type": "string", "enum": ["a"]}),
        ({"type": "array", "items": {"type": "string"}},
         {"type": "array", "items": {"type": "integer"}}),
        ({"type": "integer"}, {"type": "integer", "minimum": 10}),
    ])
    def test_witness_validity(self, old, new):
        report = analyze(old, new)
        for issue in report["issues"]:
            ce = issue["counterexample"]
            if ce is None:
                continue
            if issue["direction"] == "backward":
                source, target = old, new
            else:
                source, target = new, old
            assert compat.make_validator(source).is_valid(ce), \
                f"反例不满足 source: {ce} / {issue}"
            assert not compat.make_validator(target).is_valid(ce), \
                f"反例未违反 target: {ce} / {issue}"


class TestConditional:
    """if / then / else 条件分支（draft-07+）。

    判定规则：
    * 按实例是否命中 if 选择 then / else 分区递归比较；
    * 仅当构造出的文档满足 source 且被 target 拒绝时输出 error + 最小反例，
      否则输出 warning；
    * 未激活分支上的纯结构差异不得判为破坏（error）。
    """

    def test_then_branch_tightened_same_condition(self):
        old = {"if": {"required": ["kind"]},
               "then": {"properties": {"x": {"type": "string"}}}}
        new = {"if": {"required": ["kind"]},
               "then": {"properties": {"x": {"type": "integer"}}}}
        report = analyze(old, new)
        assert not report["backward_compatible"]
        issue = [i for i in report["issues"]
                 if i["direction"] == "backward" and i["code"] == "type_removed"][0]
        # issue.path 定位到发生变化的分支
        assert issue["path"] == "#/then/properties/x"
        assert issue["severity"] == "error"
        ce = issue["counterexample"]
        # 反例命中 if、满足旧版 then、被新版 then 拒绝
        assert "kind" in ce and ce["x"] == ""
        assert compat.make_validator(old).is_valid(ce)
        assert not compat.make_validator(new).is_valid(ce)

    def test_else_branch_tightened_same_condition(self):
        old = {"if": {"required": ["kind"]},
               "else": {"properties": {"x": {"type": "string"}}}}
        new = {"if": {"required": ["kind"]},
               "else": {"properties": {"x": {"type": "integer"}}}}
        report = analyze(old, new)
        assert not report["backward_compatible"]
        issue = [i for i in report["issues"]
                 if i["direction"] == "backward" and i["code"] == "type_removed"][0]
        assert issue["path"] == "#/else/properties/x"
        # else 分区的反例不得携带 kind（否则命中 if 走 then 分支）
        assert "kind" not in issue["counterexample"]
        assert issue["counterexample"]["x"] == ""

    def test_conditional_added_breaks_backward_only(self):
        old = {"type": "object",
               "properties": {"kind": {"type": "string"}, "x": {"type": "string"}}}
        new = {"type": "object",
               "properties": {"kind": {"type": "string"}, "x": {"type": "string"}},
               "if": {"required": ["kind"], "properties": {"kind": {"const": "a"}}},
               "then": {"required": ["y"]}}
        report = analyze(old, new)
        assert not report["backward_compatible"]
        assert report["forward_compatible"]
        issue = [i for i in report["issues"]
                 if i["direction"] == "backward" and i["code"] == "required_added"][0]
        assert issue["path"] == "#/then"
        assert issue["severity"] == "error"
        # 反例命中新版的 if（kind = "a"），缺少 then 要求的 y
        assert issue["counterexample"] == {"kind": "a"}

    def test_conditional_removed_is_backward_compatible(self):
        old = {"if": {"required": ["kind"]}, "then": {"required": ["x"]}}
        new = {}
        report = analyze(old, new)
        # 移除条件约束是放宽：向后兼容
        assert report["backward_compatible"]
        # 但旧版的条件约束会拒绝新版数据：向前不兼容
        assert not report["forward_compatible"]
        issue = [i for i in report["issues"]
                 if i["direction"] == "forward" and i["code"] == "required_added"][0]
        assert issue["path"] == "#/then"
        assert issue["severity"] == "error"

    def test_condition_changed_warns_and_locates_if(self):
        old = {"if": {"required": ["a"]}, "then": {"required": ["x"]}}
        new = {"if": {"required": ["b"]}, "then": {"required": ["x"]}}
        report = analyze(old, new)
        # 条件本身变化：#/if 上记 warning
        cond = [i for i in report["issues"] if i["code"] == "condition_changed"]
        assert cond
        assert all(i["path"] == "#/if" for i in cond)
        assert all(i["severity"] == "warning" for i in cond)
        # 命中新 if 但不命中旧 if 的实例被新版 then 拒绝：经验证的 error
        assert not report["backward_compatible"]
        err = [i for i in report["issues"]
               if i["direction"] == "backward" and i["severity"] == "error"]
        assert err and err[0]["path"].startswith("#/then")
        assert err[0]["counterexample"] == {"b": None}

    def test_inactive_branch_diff_is_warning_not_error(self):
        # 旧版数据 a 恒为 2，不可能命中 if（要求 a 为 1）：
        # then 分支的类型收紧无法构造出经过验证的反例 -> 仅 warning，不判破坏
        old = {"properties": {"a": {"const": 2}}, "required": ["a"],
               "if": {"properties": {"a": {"const": 1}}, "required": ["a"]},
               "then": {"properties": {"x": {"type": "string"}}}}
        new = {"properties": {"a": {"const": 2}}, "required": ["a"],
               "if": {"properties": {"a": {"const": 1}}, "required": ["a"]},
               "then": {"properties": {"x": {"type": "integer"}}}}
        report = analyze(old, new)
        assert report["backward_compatible"]
        issue = [i for i in report["issues"]
                 if i["direction"] == "backward" and i["code"] == "type_removed"][0]
        assert issue["path"] == "#/then/properties/x"
        assert issue["severity"] == "warning"
        assert issue["counterexample"] is None

    def test_dead_then_branch_if_false_ignored(self):
        # if:false 下 then 永远不会被激活 -> 不产生任何 issue
        old = {"type": "object"}
        new = {"type": "object", "if": False, "then": {"required": ["x"]}}
        report = analyze(old, new)
        assert report["backward_compatible"]
        assert report["forward_compatible"]
        assert report["issues"] == []

    def test_dead_else_branch_if_true_ignored(self):
        # if:true 下新增的 else 是死分支 -> 不产生 issue
        old = {"if": True, "then": {"type": "string"}}
        new = {"if": True, "then": {"type": "string"}, "else": {"type": "integer"}}
        report = analyze(old, new)
        assert report["backward_compatible"]
        assert report["issues"] == []

    def test_nested_conditional_inside_property(self):
        old = {"type": "object",
               "properties": {"addr": {"if": {"required": ["country"]},
                                       "then": {"required": ["zip"]}}}}
        new = {"type": "object",
               "properties": {"addr": {"if": {"required": ["country"]},
                                       "then": {"required": ["zip", "street"]}}}}
        report = analyze(old, new)
        assert not report["backward_compatible"]
        issue = [i for i in report["issues"]
                 if i["direction"] == "backward" and i["code"] == "required_added"][0]
        # 属性内嵌的条件：path 定位到属性下的 then 分支
        assert issue["path"] == "#/properties/addr/then"
        assert issue["counterexample"] == {"addr": {"country": None, "zip": None}}
        assert issue["counterexample_path"] == "#/addr"

    def test_nested_conditional_inside_then(self):
        old = {"if": {"required": ["a"]},
               "then": {"if": {"required": ["b"]}, "then": {"required": ["x"]}}}
        new = {"if": {"required": ["a"]},
               "then": {"if": {"required": ["b"]}, "then": {"required": ["x", "y"]}}}
        report = analyze(old, new)
        assert not report["backward_compatible"]
        issue = [i for i in report["issues"]
                 if i["direction"] == "backward" and i["code"] == "required_added"][0]
        assert issue["path"] == "#/then/then"
        # 反例同时命中两层 if，缺少最内层 then 要求的 y
        assert issue["counterexample"] == {"a": None, "b": None, "x": None}

    def test_then_false_forbids_matching_instances(self):
        old = {"type": "object", "properties": {"kind": {"type": "string"}}}
        new = {"type": "object", "properties": {"kind": {"type": "string"}},
               "if": {"required": ["kind"]}, "then": False}
        report = analyze(old, new)
        assert not report["backward_compatible"]
        issue = [i for i in report["issues"]
                 if i["direction"] == "backward"][0]
        assert issue["code"] == "schema_forbids_all"
        assert issue["path"] == "#/then"
        assert issue["severity"] == "error"

    def test_draft07_schema_keyword_conditionals(self):
        old = {"$schema": "http://json-schema.org/draft-07/schema#",
               "if": {"required": ["a"]}, "then": {"required": ["x"]}}
        new = {"$schema": "http://json-schema.org/draft-07/schema#",
               "if": {"required": ["a"]}, "then": {"required": ["x", "y"]}}
        report = analyze(old, new)
        assert not report["backward_compatible"]
        issue = [i for i in report["issues"]
                 if i["direction"] == "backward" and i["code"] == "required_added"][0]
        assert issue["path"] == "#/then"
        assert issue["severity"] == "error"

    def test_conditional_counterexamples_are_verified(self):
        # 条件分支产生的每条 error 反例都必须满足 source、被 target 拒绝
        old = {"if": {"required": ["kind"], "properties": {"kind": {"const": "a"}}},
               "then": {"required": ["y"]},
               "else": {"properties": {"n": {"type": "integer"}}}}
        new = {"if": {"required": ["kind"], "properties": {"kind": {"const": "a"}}},
               "then": {"required": ["y", "z"]},
               "else": {"properties": {"n": {"type": "string"}}}}
        report = analyze(old, new)
        errors = [i for i in report["issues"] if i["severity"] == "error"]
        assert errors
        for issue in errors:
            ce = issue["counterexample"]
            assert ce is not None
            source, target = (old, new) if issue["direction"] == "backward" else (new, old)
            assert compat.make_validator(source).is_valid(ce)
            assert not compat.make_validator(target).is_valid(ce)


class TestSamples:
    def test_sample_rejected_by_new(self):
        old = {"type": "object", "properties": {"status": {"type": "string"}}}
        new = {"type": "object", "properties": {"status": {"type": "string"}},
               "required": ["status"]}
        report = analyze(old, new, samples=[{"other": 1}])
        assert report["sample_results"][0]["valid_against_old"]
        assert not report["sample_results"][0]["valid_against_new"]
        assert any(i["code"] == "sample_rejected_by_new" for i in report["issues"])

    def test_sample_valid_both(self):
        schema = {"type": "object", "required": ["a"]}
        report = analyze(schema, schema, samples=[{"a": 1}])
        assert report["sample_results"][0]["valid_against_old"]
        assert report["sample_results"][0]["valid_against_new"]
        assert report["backward_compatible"] and report["forward_compatible"]
