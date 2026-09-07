# Shoyu Code Pro（仮称）— 欧文中間フォント計画

状態: 計画のみ（v3.3.0 時点）。名前は仮で、リブランディング時に差し替える前提。

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
| 欧文のみ | Shoyu Code Pro | ShoyuCodePro-Regular など |
| 欧文のみ NF | Shoyu Code Pro NF | ShoyuCodeProNF-Regular |
| 和文入り（現行） | Shoyu Code Pro JP / JP 35 / JP Term | 変更なし |

- OFL の Reserved Font Name により `Source` と `Monaspace` はフォント名に
  使えない（一部に含めるのも不可）。「monasource」はプロジェクトの呼び名や
  リポジトリ名には使えるが、フォントのファミリー名には使わない
- 「Shoyu Code Pro JP」の「JP なし」が欧文版、という現行の命名と自然に噛み合う
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

```
scripts/build_latin.py   # SCP VF + Monaspace VF -> dist/latin/ShoyuCodePro-*.otf
scripts/build.py         # SHS + SHCJ + dist/latin/*.otf -> dist/ShoyuCodeProJP*.otf
scripts/verify_latin.py  # 欧文単体の回帰テスト
scripts/verify.py        # JP（現行）
```

build.py から build_latin.py に移す関数: `VFSource.matched`、`draw_clean` /
`erode_path` 一式、`graft_halfwidth` の SCP 側、`replace_from_mona`、
`add_glyphs`、`add_gsub` / `_guard_subtables`、`import_scp_variants`、
`latin_blue_zones` / `add_latin_fd`、`autohint_face`、`subroutinize_face`。

build.py に残る処理: SHS の読み込み、SHCJ からの半角カナ等の複写、行間の
複写、欧文フォントからのグリフ・GSUB の取り込み（グリフ名を CID に付け替え、
lookup と feature を SHS の GSUB にマージ）、10/9 拡大（JP）、`narrow_ambiguous`
と `widen_fullwidth`（Term）、`stretch_arrows` と `add_width_alternates`、
名前・STAT・メタデータ、NF パッチ、TTC。

## 5. 段階

### 段階 1: 静的 12 面（リファクタリング）

1. `build_latin.py` を切り出し、`dist/latin/` に 12 面を出す
2. `build.py` を「欧文 OTF を読む側」に書き換える
3. **ゴールデン比較**: 書き換え前後で JP 全面のグリフアウトライン・cmap・
   GSUB の shaping 結果が一致することを CI で確認する（差が出てよいのは
   name テーブルのみ）
4. `verify_latin.py`（HarfBuzz の合字・ガード、fontbakery universal、
   メタデータ）
5. リリース資産に `ShoyuCodePro.zip`（+ NF）を追加。CHANGELOG に「欧文版」を追記

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
- **名前**: 仮称。リブランディングで変えるときは name ID 1/4/6/16、
  PostScript 名、TTC 名、リリース資産名、README の 6 か所を一括で変える
- **バージョン**: JP と同じタグで同時にリリースする（別バージョン番号を
  持たない）
