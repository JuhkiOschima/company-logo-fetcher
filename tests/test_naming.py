"""VISION.md 対応:
- 機能横断ルール「ファイル名・パスに使う外部入力は必ず無害化する」
- 機能別ルール(検索)「法人格表記は既定で除去してから検索する」
"""

from __future__ import annotations

import naming


class TestStripLegal:
    def test_removes_prefix_suffix_variants(self):
        assert naming.strip_legal("株式会社NTTデータ") == "NTTデータ"
        assert naming.strip_legal("トヨタ自動車株式会社") == "トヨタ自動車"
        assert naming.strip_legal("Sony Corporation") == "Sony"
        assert naming.strip_legal("(株)日立製作所") == "日立製作所"

    def test_does_not_empty_out_a_pure_legal_name(self):
        # 法人格しかない名前を丸ごと消してしまわない(空文字を返さない)
        assert naming.strip_legal("株式会社") == "株式会社"


class TestSafeFilename:
    def test_normal_names_pass_through_including_japanese(self):
        assert naming.safe_filename("NTTデータ") == "NTTデータ"
        assert naming.safe_filename("パナソニック／日銀") == "パナソニック／日銀"

    def test_path_separators_are_neutralized(self):
        assert naming.safe_filename("a/b:c*d") == "a_b_c_d"

    def test_traversal_attempt_is_contained(self, tmp_path):
        evil = "..\\..\\Windows\\Temp\\x"
        result = naming.safe_filename(evil)
        resolved = (tmp_path / result).resolve()
        assert resolved.parent == tmp_path.resolve()

    def test_dot_dot_alone_becomes_unnamed(self):
        assert naming.safe_filename("..") == "unnamed"
        assert naming.safe_filename(".") == "unnamed"
        assert naming.safe_filename("") == "unnamed"

    def test_reserved_windows_device_names_are_escaped(self):
        assert naming.safe_filename("CON") == "_CON"
        assert naming.safe_filename("con") == "_con"
        assert naming.safe_filename("NUL") == "_NUL"

    def test_trailing_dot_and_space_are_stripped(self):
        assert naming.safe_filename("会社名. ") == "会社名"


class TestSmartSplit:
    def test_splits_on_common_delimiters(self):
        assert naming.smart_split("トヨタ自動車/ソニーグループ") == ["トヨタ自動車", "ソニーグループ"]
        assert naming.smart_split("A社、B社、C社") == ["A社", "B社", "C社"]
        assert naming.smart_split("A社\tB社") == ["A社", "B社"]

    def test_splits_on_fullwidth_delimiters(self):
        # 実際にユーザー報告があったバグ(全角スラッシュが分解されない)の回帰
        assert naming.smart_split(
            "パナソニック／日本銀行／NHK／東京電力／武田薬品工業"
        ) == ["パナソニック", "日本銀行", "NHK", "東京電力", "武田薬品工業"]
        assert naming.smart_split("A社，B社") == ["A社", "B社"]
        assert naming.smart_split("A社；B社｜C社") == ["A社", "B社", "C社"]

    def test_single_line_falls_back_to_whitespace_split(self):
        assert naming.smart_split("トヨタ ソニー NTT") == ["トヨタ", "ソニー", "NTT"]

    def test_leading_enumeration_marks_are_stripped(self):
        assert naming.smart_split("1. トヨタ\n2. ソニー\n3) 日立") == ["トヨタ", "ソニー", "日立"]
        assert naming.smart_split("・トヨタ\n・ソニー") == ["トヨタ", "ソニー"]
        assert naming.smart_split("①トヨタ ②ソニー") == ["トヨタ", "ソニー"]

    def test_number_only_fragment_is_discarded(self):
        # 「1、トヨタ」のような貼り付けで番号だけが1要素として残らない
        assert naming.smart_split("1、トヨタ\n2、ソニー") == ["トヨタ", "ソニー"]

    def test_number_with_text_is_kept(self):
        # 数字を含むが番号だけではない企業名は残す
        assert naming.smart_split("①ヨドバシ ②109ビル") == ["ヨドバシ", "109ビル"]

    def test_duplicates_and_empty_are_removed(self):
        assert naming.smart_split("A社\tB社\tA社") == ["A社", "B社"]
        assert naming.smart_split("") == []
        assert naming.smart_split("   ") == []


class TestReadCompanyList:
    def test_ignores_blank_and_comment_lines(self, tmp_path):
        p = tmp_path / "companies.txt"
        p.write_text("トヨタ自動車\n\n# コメント\nソニーグループ\nトヨタ自動車\n", encoding="utf-8")
        assert naming.read_company_list(p) == ["トヨタ自動車", "ソニーグループ"]
