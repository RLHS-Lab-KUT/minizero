#!/usr/bin/env python3
"""cfg_dump.py — エンジンの stderr から cfg ダンプを取り出して辞書にする。

背景 [事実]:
  minizero は起動時に読み込んだ全設定を stderr へ吐く。
  mode_handler.cpp:118-131 readConfiguration() の実行順は
    :120 cl.loadFromFile(config_file)      … -conf_file
    :124 cl.loadFromString(config_string)  … -conf_str
    :129 std::cerr << cl.toString()        … ダンプ
  なのでダンプは -conf_str による上書き「後」の値である。

出力形式 [事実]:
  ConfigureLoader::toString() (configure_loader.cpp:64-73) は
  グループごとに "# <グループ名>" の見出し行 → 各パラメータ → 空行 を出す。
  1 パラメータの書式は Parameter::toString() (configure_loader.h:51-59):
    - 説明が 150 文字以下 … "key=value # 説明"
    - 説明が 150 文字超   … "# 説明" を前行に出し、次行は "key=value" だけ
  値の文字列化は getParameter<T>() (configure_loader.h:24-30)。
  bool のみ特殊化があり "true"/"false" を返す (configure_loader.cpp:26-32)。

打ち切り [事実]:
  ダンプの直後、mode_handler.cpp:69 が "(Version: <hash>)" を stderr に出す。
  その後は genmove ごとに盤面表示と探索情報 (zero_actor.cpp:52、
  console.cpp:170 が display_board=true を渡す) と
  "Spent Time = N.NN (s)" (console.cpp:171) が延々と流れる。
  したがって "(Version:" の行で打ち切り、かつキーの形 (^[a-z][a-z0-9_]*=)
  にマッチする行だけを拾う。二重の防御にしてある。

othello ビルドで登録されるパラメータは 59 個 (configuration.cpp:92-205、
ゲーム別ブロック :164-196 に OTHELLO の枝はないので env_board_size のみ)。

使い方:
  モジュールとして  from cfg_dump import parse_cfg_dump
  CLI として        python3 xrl_viz/cfg_dump.py <stderrファイル>
                    → JSON を stdout に出す
"""
import json
import re
import sys

# othello ビルドで ConfigureLoader に登録されるパラメータ数
EXPECTED_NUM_PARAMS = 59

# ダンプの終端。mode_handler.cpp:69 が readConfiguration() の直後に出す。
VERSION_MARKER = "(Version:"

# "key=value" のキー側。configuration.cpp の addParameter 第1引数はすべてこの形。
# "Spent Time = ..." (キーに空白)、"  root node info: p = ..." (先頭空白)、
# "[policy] ..." はこの正規表現で落ちる。
KEY_VALUE_RE = re.compile(r"^([a-z][a-z0-9_]*)=(.*)$")


def parse_cfg_dump(text):
    """cfg ダンプを含むテキストから {key: value} を作る。value は文字列のまま。

    text は str でも bytes でもよい。bytes の場合は UTF-8 として、
    デコードできないバイト (盤面表示の ANSI やロケール依存文字) は置換する。
    """
    if isinstance(text, bytes):
        text = text.decode("utf-8", errors="replace")

    config = {}
    for line in text.splitlines():
        # ダンプは必ず先頭にあり、"(Version:" 行より後は探索ログなので見ない。
        if VERSION_MARKER in line:
            break
        # グループ見出し行 ("# Program") と、150 文字超の説明が単独で置かれた行、
        # および空行はここで落ちる。
        m = KEY_VALUE_RE.match(line)
        if not m:
            continue
        key, value = m.group(1), m.group(2)
        # 説明が 150 文字以下のときは " # 説明" が同じ行に続く (configure_loader.h:56)。
        # 値そのものに '#' が入る登録済みパラメータは無い。
        if "#" in value:
            value = value.split("#", 1)[0]
        config[key] = value.strip()
    return config


def parse_cfg_dump_file(path):
    """ファイルを読んで parse_cfg_dump に渡す。bytes で読むので文字化けで落ちない。"""
    with open(path, "rb") as f:
        return parse_cfg_dump(f.read())


def main(argv):
    if len(argv) != 2:
        sys.exit("使い方: python3 xrl_viz/cfg_dump.py <stderrファイル>")
    config = parse_cfg_dump_file(argv[1])
    if len(config) != EXPECTED_NUM_PARAMS:
        sys.exit(f"[cfg_dump] 致命的: cfg のキーが {len(config)} 件、"
                 f"期待 {EXPECTED_NUM_PARAMS} 件。パースに失敗している")
    json.dump(config, sys.stdout, ensure_ascii=False)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main(sys.argv)
