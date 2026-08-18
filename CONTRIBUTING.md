# Contributing

Shoyu Code Pro JP は上流フォント（Source Han Sans JP / Source Code Pro /
Monaspace / Source Han Code JP）を CI 上で合成して作られています。ソース
グリフを直接同梱していないため、ビルドには毎回それらの上流ファイルが
必要です。

## ローカルビルド

```sh
pip install -r requirements.txt
```

以下の環境変数（すべて必須）を渡して `scripts/build.py` を実行します。

| 変数 | 内容 | 入手元 |
|------|------|--------|
| `SHS_DIR` | `SourceHanSansJP-<Weight>.otf` が入ったディレクトリ | [Source Han Sans Releases](https://github.com/adobe-fonts/source-han-sans/releases) |
| `SCP_VF_U` | `SourceCodeVF-Upright.otf` へのパス | [Source Code Pro Releases](https://github.com/adobe-fonts/source-code-pro/releases) |
| `SCP_VF_I` | `SourceCodeVF-Italic.otf` へのパス | 同上 |
| `MONA_VF` | Monaspace の可変フォント（例: `Monaspace Neon Var.ttf`） | [Monaspace Releases](https://github.com/githubnext/monaspace/releases) |
| `SHCJ_TTC` | `SourceHanCodeJP.ttc` へのパス（省略時 `upstream/SourceHanCodeJP.ttc`） | [Source Han Code JP Releases](https://github.com/adobe-fonts/source-han-code-jp/releases) |

取得元の URL パターンや正確なタグは `.github/workflows/ci.yml` /
`release.yml` の `Fetch upstreams` ステップを参照してください（そのまま
実行可能なリファレンスです）。

```sh
SHS_DIR=... SCP_VF_U=... SCP_VF_I=... MONA_VF=... SHCJ_TTC=... \
  python scripts/build.py            # 全ファミリー
  python scripts/build.py "Regular"  # Regular系のみ（動作確認用、速い）
```

## テスト・検証

```sh
python scripts/verify.py dist/ShoyuCodeProJP-Regular.otf
```

グリフの合成漏れやメトリクスの崩れなど、シェイピングまわりの回帰を
チェックします。変更を提出する前に、少なくとも `Regular` 面で通ることを
確認してください。CI（`.github/workflows/ci.yml`）でも push / PR 時に
同じ検証が走ります。

NF（Nerd Fonts）変種の生成を試す場合:

```sh
python scripts/nerdpatch.py <FontPatcher dir>
```

## 合字を追加・変更する（`data/mona_ligs.json`）

合字の定義は `data/mona_ligs.json` にあり、`scripts/build.py` の
`add_glyphs()` / `add_gsub()` が読み取ります。1エントリの形式:

```jsonc
"!=": {
  "cells": 2,                       // 合字が占める半角セル数（送り幅 = CELL * cells）
  "glyphs": ["exclam_equal"],       // Monaspace VF 側のグリフ名（複数可、左から順に並べて描画）
  "group": "ss01"                   // 属する stylistic set（calt/liga には自動的に全グループが載る）
}
```

- **キー**: 合字として認識させたい文字列そのもの（例 `"!="`）。この文字列の
  各文字が出力フォントの cmap に存在しないとスキップされます。
- **`glyphs`**: Monaspace VF 側のグリフ名のリスト。単一グリフなら1要素、
  複数グリフを並べて1つの合字にする場合は複数要素（左詰めで並べて描画）。
  ここに書いたグリフ名が Monaspace 側に存在しないとスキップされます。
- **`cells`**: 合字の見た目上の幅（半角セル単位）。通常は文字列の文字数と
  一致させます。
- **`group`**: `ss01`〜`ss08` のいずれか。README の「合字一覧」表にある
  グループ分け（比較・矢印・マークアップ・パイプ・コロン・ドット・
  コメント・反復論理）に対応し、対応する stylistic set 機能として
  個別に有効化できるようになります。既存グループの内容は README を参照。

新しい合字を追加する手順:

1. 対象の記号列を Monaspace 側の GSUB/グリフ名で確認する（Monaspace の
   ソースまたはフォント自体をのぞいて `xxx_yyy` 形式のグリフ名を探す）。
2. `data/mona_ligs.json` に上記形式でエントリを追加する。
3. `python scripts/build.py "Regular"` でビルドし、`scripts/verify.py`
   で確認する。
4. README の合字一覧・該当する ss テーブル行も実態に合わせて更新する
   （存在しない合字を書かない・書き漏らさないこと）。

`.alt` サフィックス付きグリフ（例 `exclam_exclam.alt`）が Monaspace 側に
存在する場合、`cv99`（演算子の代替デザイン切り替え）として自動的に
取り込まれます。

## 上流のバージョンピンを更新する

上流の固定タグは `.github/actions/fetch-upstreams/action.yml` の
「Pin upstream releases」ステップ（`SHS_TAG` / `SCP_TAG` / `SCP_VF_ZIP` /
`MONA_TAG` / `SHCJ_TAG`）に一元化されており、`ci.yml` / `release.yml` は
このアクションを共有しています。

通常は手で更新する必要はありません。`upstream-sync.yml`（毎週月曜 実行、
`workflow_dispatch` でも起動可）が検知から出荷までを通しで回します:

1. `scripts/bump_pins.py` が各上流の `releases/latest` を引き、ピンを書き
   換える（ダウンロード URL を事前に HEAD で検証するので、上流がアセット
   名を変えた場合はここで落ちる）。
2. `chore/upstream-sync` ブランチに PR を作成する。
3. CI（`lint-test` / `build`）が緑になるのを待って squash マージする。
4. パッチを 1 つ上げたタグで `release.yml` を dispatch する。

Issue は起票しません。PR 自体が同じ情報に加えて「そのピンでビルドが通る」
証拠を持っているためです。

新しい上流が字形を劣化させている場合は **PR を閉じてください**。ピンは
据え置かれ、翌週の実行で PR が開き直ります。恒久的に追従したくない場合は
`scripts/bump_pins.py` の対象から外します。

見た目に影響しうる変更（合字・ウェイトマッチング・グリフ形状など）が
あった場合は、README の該当箇所（`=`バーの実測値など）も見直してください。
これは自動化の対象外です。

手で追従する場合は `.github/actions/fetch-upstreams/action.yml` のピンを
書き換えるだけで済みます（キャッシュキーはピンから自動導出される）。

## Issue / Pull Request

バグ報告には `.github/ISSUE_TEMPLATE/` のテンプレートを利用して
ください（上流更新は `upstream-sync.yml` が PR で扱うため、Issue の
テンプレートはありません）。Pull Request は変更内容と動作確認方法（実行した
`verify.py` の対象面など）を簡潔に記載してください。
