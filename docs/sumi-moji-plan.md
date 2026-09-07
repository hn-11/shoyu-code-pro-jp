# Sumi Moji（仮称）— 欧文中間フォント計画

状態: 段階 1a まで実装済み（v3.3.0）。`scripts/build_latin.py` が 35
ファミリーの完成した OTF から欧文レイヤーを切り出して `SumiMoji-*.otf`
12面をビルドし、`SumiMoji.zip` としてリリース資産に含まれている。
段階 1b（下記）以降は未着手。名前は仮称 **Sumi Moji**（墨文字）。
衝突調査済み（フォント・技術領域で同名なし、商標は未確認、
`sumimoji.com` / `.net` は取得済みで `.dev` / `.jp` は空き）。

## 1. 目的

Shoyu Code Pro JP の欧文層（Source Code Pro の文字 + Monaspace の記号・合字）を
**独立した欧文フォントとして先に完成させ**、JP はそれを Source Han Sans に
載せるだけの工程にする。

- 欧文側の設計判断を 1 か所に集める: 記号の Monaspace 化、合字の文脈ガード、
  太さ合わせ、ヒントのアライメントゾーン、Light の削り（Monaspace wght 下限対策）
- 欧文フォント単体で HarfBuzz / fontbakery / 実機（Windows Terminal, iTerm2）の
  検証を回せるようにする。JP 側の検証は「和文と幅」に絞れる
- JP / 35 / Term の 3 ファミリーが同じ中間物から出るので、ファミリー間の
  欧文の差が構造的に消える
- 和文が不要な利用者向けに、そのまま配布物になる

描画結果は現行と同じものを目標にする（リファクタリングであって再設計ではない）。

## 2. 命名（仮）

| 用途 | ファミリー名 | PostScript 名 |
|---|---|---|
| 欧文のみ | Sumi Moji | SumiMoji-Regular など |
| 欧文のみ NF | Sumi Moji NF | SumiMojiNF-Regular |
| 和文入り | Sumi Moji JP / Sumi Moji JP 35 / Sumi Moji JP Term | SumiMojiJP-Regular, SumiMojiJP35-Regular, SumiMojiJPTerm-Regular |
| 和文入り NF | Sumi Moji JP NF など | SumiMojiJPNF-Regular など |

リブランディング時に現行の Shoyu Code Pro JP から名前を変える箇所（一括で変更する）:

1. `scripts/build.py` の `set_names`（family / PostScript 名のプレフィックス）と `PROJECT_URL` / `PROJECT_COPYRIGHT`
2. `scripts/nerdpatch.py` の NF 命名正規表現
3. `scripts/makeotc.py` の TTC ファイル名
4. `.github/workflows/release.yml` のリリース資産名と `SHOYU_VERSION` 環境変数名
5. `scripts/verify.py` の `FAMILY_METRICS` 判定（ファミリー名のトークン）
6. README / CHANGELOG / LICENSE の名前と、リポジトリ名・`git remote`

- OFL の Reserved Font Name により `Source` と `Monaspace` はフォント名に
  使えない。OFL FAQ 5.4 は「RFN の単語全体は不可、単語の一部は可だが非推奨」
  で、`Monasource` は `Source` を丸ごと含むため不可側。`Sumi Moji` は
  どちらの RFN も含まない
- 名前の由来: 墨文字（筆で書いた文字）。`Sumi` 単体は筆文字系フォント名で
  多用されるが、`Sumi Moji` 複合名のフォントは無い。日本に同名の工芸系
  小規模ブランド（T シャツ、ネイル筆、書道用品店「墨文字製作所」）がある
- name ID 0 / 9 のドナー表記、achVendID `SHYU`、STAT、WWS は JP と同じ規約

## 3. 仕様

### 3.1 グリフセット

- Source Code Pro VF の全レパートリー（ラテン・ギリシャ・キリル・記号・
  結合文字・罫線）。SCP 原寸（600 セル、1000 em）
- ASCII 記号 32 字と合字 50 種は Monaspace（現行と同じ選定、`data/mona_ligs.json`）
- `← → ↑ ↓ ⇐ ⇒ ⇔ ≠ ≤ ≥ …` は **1 セルの Monaspace 版を既定**にする
  （欧文フォントに全角は無い。JP で使う全角版は JP 側で合字グリフから切り出す、
  現行 `stretch_arrows` のまま）
- 合字グリフは現行どおり n セル幅の 1 グリフ（LigatureSubst）。Fira Code 式の
  スペーサー方式（VS Code 統合ターミナル対応）はスコープ外、別課題

### 3.2 GSUB / GPOS

- `calt` / `liga`: 合字 50 種 + 文脈ガード（入力列を全構成グリフでカバーする
  トリガールール、最長一致順）
- `ss01`〜`ss08`: 合字グループ、`cv99`: .alt 字形。`ss09` は JP 専用
  （欧文版は既定が 1 セルなので不要）
- SCP 由来: `zero` `salt` `cv01`〜`cv17` `ss11`〜`ss17`（+10 マウントは JP との
  整合のため維持）
- GPOS は持たない（等幅。SCP VF の `kern` は取り込まない）

### 3.3 メトリクス

- 送り 600、UPM 1000、行間は SCP の宣言値（hhea / OS/2 typo・win）。JP に
  載せるときは現行どおり SHCJ の行間に差し替える
- `post.isFixedPitch=1`、PANOSE proportion 9、xAvgCharWidth は実計算、
  sxHeight / sCapHeight は実測（JP と同じ関数）

### 3.4 ウェイト

- 段階 1（静的）: JP と同じ 6 ウェイト × 2 スタイル。各面の太さは
  **SHCJ の `=` バー厚に一致**させる（現行の二分探索）。名前は JP と同じ
  Light / Normal / Regular / Medium / Bold / Heavy
- 段階 2（VF）: wght 軸 200〜900（SCP の範囲）。JP はこの VF を SHCJ の
  バー厚に合う wght でインスタンス化して使う。Term の太さ補正（600 セルのまま
  バー 69）も「少し重い wght でインスタンス化する」だけになり、現行の
  「拡大→削り」の工程が不要になる

### 3.5 ヒント

- 面ごとに専用 FontDict（測定したゾーン）+ otfautohint、cffsubr でサブルーチン化
  （現行 v3.3.0 の仕組みをそのまま移す）
- VF（CFF2）は otfautohint が対応しているが、ヒントはデフォルト
  マスターのみに乗る。静的インスタンスを配布するならインスタンス後に付け直す

## 4. ビルド構成

現在（段階 1a、実装済み）: `build_latin.py` は VF からではなく、
`build.py` が組み上げた 35 の完成品 OTF を切り出す側になっている
（`build.py` 自体は今も SHS + SCP VF + Monaspace VF + SHCJ から毎回
独立に組む。以下は段階 1b で置き換える計画のまま）。

```
scripts/build.py         # SHS + SCP VF + Monaspace VF + SHCJ
                          #   -> dist/ShoyuCodeProJP*.otf（JP/35/Term、現行どおり）
scripts/build_latin.py   # dist/ShoyuCodeProJP35-*.otf（段階1aの入力）
                          #   -> dist/latin/SumiMoji-*.otf
scripts/verify_latin.py  # 欧文単体の回帰テスト（dist/latin/SumiMoji-*.otf）
scripts/verify.py        # JP（現行）
```

計画（段階 1b、未着手）:

```
scripts/build_latin.py   # SCP VF + Monaspace VF -> dist/latin/SumiMoji-*.otf
scripts/build.py         # SHS + SHCJ + dist/latin/*.otf -> dist/ShoyuCodeProJP*.otf
```

build.py から build_latin.py に移す関数（段階1bで実施、1aでは未実施—
build.py は現行のまま VF から直接組んでいる）: `VFSource.matched`、
`draw_clean` / `erode_path` 一式、`graft_halfwidth` の SCP 側、
`replace_from_mona`、`add_glyphs`、`add_gsub` / `_guard_subtables`、
`import_scp_variants`、`latin_blue_zones` / `add_latin_fd`、
`autohint_face`、`subroutinize_face`。

build.py に残る処理: SHS の読み込み、SHCJ からの半角カナ等の複写、行間の
複写、欧文フォントからのグリフ・GSUB の取り込み（グリフ名を CID に付け替え、
lookup と feature を SHS の GSUB にマージ）、10/9 拡大（JP）、`narrow_ambiguous`
と `widen_fullwidth`（Term）、`stretch_arrows` と `add_width_alternates`、
名前・STAT・メタデータ、NF パッチ、TTC。

## 5. 段階

### 段階 1a: 35 から切り出し（実装済み、v3.3.0）

1. ✅ `build_latin.py` を切り出し、`dist/ShoyuCodeProJP35-*.otf`
   （`build.py` が既にビルドした 35 面）から `dist/latin/` に
   `SumiMoji-*.otf` 12 面を出す
2. ✅ `verify_latin.py`（HarfBuzz の合字・ガード、メタデータ、GSUB の
   構成）
3. ✅ リリース資産に `SumiMoji.zip`（LICENSE 同梱）を追加。CHANGELOG に
   「欧文版」を追記。`ci.yml` は Regular ペアをビルド・検証、
   `release.yml` は 12 面をビルドし 2 面を検証
4. 未着手: Nerd Fonts 変種、TTC 化

### 段階 1b: build.py が欧文フォントを消費する側に書き換え（未着手）

1. `build_latin.py` の入力を 35 の完成品 OTF から SCP VF + Monaspace VF
   直接に変える（段階 1a は既存の 35 ビルドに依存する中間形態）
2. `build.py` を「欧文 OTF（`dist/latin/*.otf`）を読む側」に書き換える
3. **ゴールデン比較**: 書き換え前後で JP 全面のグリフアウトライン・cmap・
   GSUB の shaping 結果が一致することを CI で確認する（差が出てよいのは
   name テーブルのみ）
4. fontbakery universal チェックを `verify_latin.py` に追加

見積り: 数日。描画結果は変わらない。

### 段階 2: VF

1. デザインスペース: SCP VF の 3 マスター（wght 200 / 約 458 / 900。CFF2 の
   VarStore 領域から）に合わせ、各マスター位置で Monaspace を**太さ一致で
   インスタンス化**した静的マスターを用意する。Monaspace の wght 下限 200
   で足りない最軽量マスターは現行の erosion で削る
2. fontTools varLib でマスター群から CFF2 VF を組む（Upright / Italic は
   SCP と同じく別ファイル）。Monaspace 由来グリフは Monaspace VF の補間互換
   アウトラインから来るので互換性は保てるが、pathops の simplify を通すと
   点数が変わるため、**simplify は VF では使わず**重なりは残す（Adobe の
   VF と同じ扱い）
3. STAT / fvar のインスタンス名は段階 1 と同じ 6 ウェイト
4. JP 側は `VFSource.matched` で欧文 VF をそのまま使う（今 SCP VF と
   Monaspace VF に対して別々にやっていることが 1 回になる）
5. 静的 12 面は VF からインスタンス化して配布（ヒントはインスタンス後に付与）

見積り: 数日〜1 週間。未確定要素が多いので段階 1 の後に着手する。

## 6. リスク・未決事項

- **重なり除去 vs 補間互換**: 静的版では pathops で重なりを除去しているが、
  VF ではマスター間の点対応が崩れる。VF は重なりを残し、静的インスタンスで
  除去する二本立てにする
- **Light の削り**: erosion は非線形なので VF では補間で再現できない。
  Light 相当をマスターに立てる
- **太さの線形性**: SHCJ の各面に対する wght の一致点は二分探索で求めている。
  VF の中間ウェイトで Monaspace と SCP の太さがどの程度ずれるかは
  マスターを置く位置に依存する。誤差 1u を超える場合はマスターを増やす
- **Italic**: SCP Italic は −12°、Monaspace の slnt は −11° が下限。
  残り 1° のシアーは現行どおりマスター生成時に掛ける
- **名前**: 仮称 Sumi Moji。商標（USPTO / J-PlatPat）はこの環境から未確認、
  確定前に直接引く。変更箇所の一覧は 2 節
- **バージョン**: JP と同じタグで同時にリリースする（別バージョン番号を
  持たない）
