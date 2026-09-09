# Sumi Moji — 欧文中間フォント計画

状態: 段階 1（1a・1b とも）・段階 2（VF 化）とも実装済み。v5.0.0 で
基準を英語圏のターミナルフォントに置き換えた（下の「v5」節）。
`scripts/build_latin.py` が Source Code Pro VF + Monaspace VF から直接
Sumi Moji（`dist/latin`）を組み、`scripts/build.py` はそれを Source Han
Sans に接ぎ木する側になった（VF には直接触れない）。
`scripts/build_latin_vf.py` が同じレシピを CFF2 可変フォントとして組む
（`dist/latin/SumiMoji[wght].otf` / `SumiMoji-Italic[wght].otf`）。
`SumiMoji.zip` は VF 2 面（静的 10 面は JP 面のドナー・NF パッチの入力・
VF の検証に使い、配布しない）。名前は **Sumi Moji**（墨文字）で確定し、
和文入りは **Sumi Moji JP**（v3.2.0 までの Shoyu Code Pro JP を改名。
2 節の一覧はリポジトリ名を除き実施済み）。衝突調査済み（フォント・技術
領域で同名なし、商標は未確認、`sumimoji.com` / `.net` は取得済みで
`.dev` / `.jp` は空き）。

## v5: 基準を英語圏のターミナルフォントに

v4.0.0 までは Source Han Code JP（SHCJ）が基準だった: 2:3 の比率、SHCJ の
行間（1.453 em）、SHCJ の `=` バーに Latin の太さを寄せる主従、SHCJ の
半角/全角の割り当て。v5.0.0 で基準を欧文側（Source Code Pro）に置き換え、
SHCJ は上流から外れた。

- **セルは 600、既定は 3:5**。Sumi Moji（SCP 原寸）に Source Han Sans を
  そのまま載せる。2:3（旧基本ファミリー）と 35 は廃止、Term（1:2）は
  全角の送りを 2 セルに広げるだけの変種として残す。
- **行間は SCP の 984 / −273（1.257 em）**。hhea = typo、
  `USE_TYPO_METRICS`。win は Source Han Sans の宣言値（1160 / 288）。
- **太さの主従を逆転**。Latin は SCP の名前付きインスタンス（Light 300 /
  Regular 400 / Medium 500 / SemiBold 600 / Bold 700）そのもの、和文は
  `＝` のバーが合う Source Han Sans の面を実測で選ぶ（ExtraLight / Normal /
  Regular / Medium / Bold）。Normal と Heavy は消え、ウェイト名は英語
  フォントの体系になった。VF の wght 軸は SCP の wght と一致（恒等写像）。
- **幅の方針**: Sumi Moji が持つ文字はすべて 1 セル（ギリシャ・キリル・
  罫線・矢印 7 種と `≠ ≤ ≥ …` も）。JIS 流の全角字形は `fwid` で戻す
  （矢印は合字から切り出した全角版、その他は Source Han Sans の全角
  グリフか同フォントの `fwid` 形）。`hwid` / `ss09` の幅切り替えは不要に
  なり廃止。Source Han Sans の比例幅の残り（半角カナ 500、Hangul 字母
  920、ﬀ、⸻）はセルか全角の倍数に中央配置（`fit_to_grid`）。
- **東アジア文字幅が Wide の 13 字（`☕` `🎵` `🎶` `💩` `🔒` `🤖`、Hangul
  声調記号 2 字、注音の入声 5 字）は 1 セルのまま**。両ドナーがそう描いて
  いて、これより広い字形を持たないため。ターミナルは 2 桁分を空けるので
  左寄りに見える。2 セルに広げるかは未決（README の「幅の方針」に明記）。
- **Nerd Fonts 版の命名は本家の流儀**: アイコンを 1 セルに収めるので
  `<Family> Nerd Font Mono` / `<PSFamily>NFM`。v5.1 で font-patcher と
  FontForge を捨て、本家の `Symbols Nerd Font Mono` から fontTools で
  接ぎ木する（同じ記号集合・同じ相対寸法、1 面 10 秒、CID 構造もメタ
  データもそのまま）。本家の立場は「フォールバック ＞ パッチ／合成」で、
  合成でも記号集合と寸法を本家に合わせ、名前に Nerd Font を含め、出典の
  ライセンスを添える——この 3 点を満たしている。
- **SHCJ 依存の解消**: バーの目標値（Latin が固定なので不要）、半角カナ
  のドナー（Source Han Sans 自身の 500 幅を中央配置）、行間（SCP）、
  半角の集合（Sumi Moji の cmap）。`SHCJ_TTC` と `SHCJ_TAG` は消えた。

英語フォント基準で判断した残りの課題（優先順）: README の見本画像、
fontbakery を CI に、VS Code 統合ターミナル（xterm.js）の合字、Homebrew
cask / Scoop、リポジトリ名と `PROJECT_URL` の改名。合字なし変種
（JetBrains Mono NL / Cascadia Mono 相当）は需要が出てから。Nerd Fonts の
記号を本体に同梱する案（Cascadia 流）は、本家が名前で識別できることを
望んでいる以上、NF 付きの別ファミリーのままにする。

## 1. 目的

Sumi Moji JP の欧文層（Source Code Pro の文字 + Monaspace の記号・合字）を
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

## 2. 命名

| 用途 | ファミリー名 | PostScript 名 |
|---|---|---|
| 欧文のみ | Sumi Moji | SumiMoji-Regular など |
| 欧文のみ NF | Sumi Moji Nerd Font Mono | SumiMojiNFM-Regular |
| 和文入り | Sumi Moji JP / Sumi Moji JP Term | SumiMojiJP-Regular, SumiMojiJPTerm-Regular |
| 和文入り NF | Sumi Moji JP Nerd Font Mono など | SumiMojiJPNFM-Regular など |

リブランディングで Shoyu Code Pro JP から名前を変えた箇所（リポジトリ名と
`PROJECT_URL` を除き実施済み。リポジトリを改名すれば GitHub は旧 URL を転送する）:

1. `scripts/build.py` の `set_names`（family / PostScript 名のプレフィックス）と `PROJECT_URL` / `PROJECT_COPYRIGHT`
2. `scripts/nerdpatch.py` の NF 命名正規表現
3. TTC のファイル名（のちに TTC 自体を廃止）
4. `.github/workflows/release.yml` のリリース資産名と `SUMI_VERSION` 環境変数名
5. `scripts/verify.py` の `FAMILY_METRICS` 判定（ファミリー名のトークン）
6. README / CHANGELOG / LICENSE の名前と、リポジトリ名・`git remote`

命名上の注意:


- OFL の Reserved Font Name により `Source` と `Monaspace` はフォント名に
  使えない。OFL FAQ 5.4 は「RFN の単語全体は不可、単語の一部は可だが非推奨」
  で、`Monasource` は `Source` を丸ごと含むため不可側。`Sumi Moji` は
  どちらの RFN も含まない
- 名前の由来: 墨文字（筆で書いた文字）。`Sumi` 単体は筆文字系フォント名で
  多用されるが、`Sumi Moji` 複合名のフォントは無い。日本に同名の工芸系
  小規模ブランド（T シャツ、ネイル筆、書道用品店「墨文字製作所」）がある
- name ID 0 / 9 のドナー表記、achVendID `SUMI`、STAT、WWS は JP と同じ規約

## 3. 仕様

### 3.1 グリフセット

- Source Code Pro VF の全レパートリー（ラテン・ギリシャ・キリル・記号・
  結合文字・罫線）。SCP 原寸（600 セル、1000 em）
- ASCII 記号 32 字と合字 61 種は Monaspace（現行と同じ選定、`data/mona_ligs.json`）
- `← → ↑ ↓ ⇐ ⇒ ⇔ ≠ ≤ ≥ …` は **1 セルの Monaspace 版を既定**にする
  （欧文フォントに全角は無い。JP で使う全角版は JP 側で合字グリフから切り出す、
  現行 `stretch_arrows` のまま）
- 合字グリフは現行どおり n セル幅の 1 グリフ（LigatureSubst）。Fira Code 式の
  スペーサー方式（VS Code 統合ターミナル対応）はスコープ外、別課題

### 3.2 GSUB / GPOS

- `calt` / `liga`: 合字 61 種 + 文脈ガード（入力列を全構成グリフでカバーする
  トリガールール、最長一致順）
- `ss01`〜`ss08`: 合字グループ、`cv99`: .alt 字形（`ss09` の幅切り替えは
  v5 で廃止: 既定が 1 セル、全角は `fwid`）
- SCP 由来: `zero` `salt` `cv01`〜`cv17` `ss11`〜`ss17`（+10 マウントは JP との
  整合のため維持）
- GPOS は SCP 自身のもの（結合文字の `mark` / `mkmk`、`frac`、`size`）を保持。`kern` は無い（等幅）

### 3.3 メトリクス

- 送り 600、UPM 1000。行間は SCP の hhea 値（984 / -273）で、OS/2 typo を同じ値にして
  USE_TYPO_METRICS を立て、win はファミリー全面のバウンディングボックスの最大値。JP に
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

- SCP VF をインスタンス化するとヒントが落ちる（fontTools の CFF2 インスタンサ）ため、
  SCP 自身のアライメントゾーン（Private の BlueValues 等。インスタンス化で
  ペアが逆順になることがあるので並べ直す）に対して全グリフを otfautohint で
  ヒント付けし、cffsubr でサブルーチン化。JP 側は接ぎ木後に自分のゾーンで付け直す
- VF（CFF2）は otfautohint が対応しているが、ヒントはデフォルト
  マスターのみに乗る。静的インスタンスを配布するならインスタンス後に付け直す

## 4. ビルド構成

実装済み（段階 1a・1b とも）。実際のパイプライン:

```
scripts/build_latin.py   # SCP VF + Monaspace VF
                          #   -> dist/latin/SumiMoji-*.otf（配布物、35と同じ太さ）
                          #   -> dist/latin/term/SumiMojiTerm-*.otf（内部専用、Term用の太さ）
scripts/build.py         # SHS + SHCJ + dist/latin{,/term}
                          #   -> dist/SumiMojiJP*.otf（JP/35/Term）
scripts/verify_latin.py  # 欧文単体の回帰テスト（dist/latin/SumiMoji-*.otf）
scripts/verify.py        # JP（現行）
scripts/golden.py        # 2つの dist ディレクトリを比較（cmap・送り幅・
                          #   シェーピング・アウトライン・メタデータ・ヒント）
```

`build.py` は SCP VF・Monaspace VF に直接触れなくなり、`scripts/build_latin.py`
が先に走って `dist/latin`（および `dist/latin/term`）を作っていることを
前提にする（`LATIN_DIR` 環境変数、既定 `dist/latin`）。VF のインスタンス化・
太さ二分探索・合字/記号の合成・グラフト用ヘルパー（`VFSource.matched`、
`draw_clean` / `erode_path`、`replace_from_mona`、`add_glyphs`、`add_gsub` /
`_guard_subtables`、`import_scp_variants`、`latin_blue_zones` /
`add_latin_fd`、`autohint_face`、`subroutinize_face` など）は `build.py`
モジュールに残ったまま `build_latin.py` から import されて使われる形で、
別モジュールへの複製はしていない。`build.py` 側は同じ関数群を、VF
インスタンスではなく `dist/latin` の完成品 OTF（`graft_halfwidth`,
`import_scp_variants`, `latin_ligatures`, `latin_onecell` 等が受け取る）
に対して呼び出すだけになった。

build.py に残る処理: SHS の読み込み、SHCJ からの半角カナ等の複写、行間の
複写、Sumi Moji からのグリフ・GSUB の取り込み（グリフ名を CID に付け替え、
lookup と feature を SHS の GSUB にマージ）、10/9 拡大（JP）、`narrow_ambiguous`
と `widen_fullwidth`（Term）、`stretch_arrows` と `add_width_alternates`、
名前・STAT・メタデータ、NF パッチ。

JP 側の出力は、書き換え前（VF を直接読んでいた頃）とグリフアウトライン・
cmap・GSUB の shaping 結果が roundoff（±1〜2ユニット）を除いて一致する
ことを目標にしており、`scripts/golden.py` で2つの dist ディレクトリを
比較して確認する。

## 5. 段階

### 段階 1a: 35 から切り出し（実装済み、のち段階 1b で置き換え）

最初の実装。`build_latin.py` を切り出し、`dist/SumiMojiJP35-*.otf`
（`build.py` が既にビルドした 35 面）から `dist/latin/` に
`SumiMoji-*.otf` 12 面を出す中間形態だった。`verify_latin.py` と
`SumiMoji.zip` のリリース資産化はこの段階で入り、以降も引き継がれている。
段階 1b の実装により、35 の完成品 OTF を経由する経路そのものは
置き換わっている。

### 段階 1b: build_latin.py が VF から直接組み、build.py が消費する（実装済み、v4.0.0）

1. ✅ `build_latin.py` の入力を 35 の完成品 OTF から SCP VF + Monaspace VF
   直接に変えた: SCP VF のインスタンスを CFF2ToCFF で静的 CID-keyed CFF
   化し、Monaspace の合字・記号・1セル矢印を接ぎ木、otfautohint で
   再ヒントして cffsubr でサブルーチン化（4節参照）
2. ✅ `build.py` を「欧文 OTF（`dist/latin` / `dist/latin/term`）を読む側」
   に書き換えた（`SHS_DIR` / `SHCJ_TTC` / `LATIN_DIR` のみを見る。
   `ci.yml` / `release.yml` とも `build_latin.py` を先に実行する）
3. ✅ **ゴールデン比較**: `scripts/golden.py` を追加し、2つの dist
   ディレクトリ間で cmap・送り幅・シェーピング・アウトライン（許容誤差
   付き）・メタデータ・CFF ヒントを比較できるようにした
4. 未着手: fontbakery universal チェックの `verify_latin.py` への追加

見積り: 数日。描画結果は変わらない（実績: roundoff ±1〜2ユニットの差を
除き一致）。

### 段階 2: VF（実装済み、v4.0.0、`scripts/build_latin_vf.py`）

1. ✅ デザインスペース: SCP VF 自身のマスター位置——**wght 200 / 400**
   （事前の見積りは「約 458」だったが、CFF2 の VarStore 領域のピークを
   avar/fvar 経由で逆算すると実際は 400 だった。決め打ちせず
   `build_latin_vf.confirm_scp_master_wghts` が毎回読み直す）に **Regular
   と Heavy の位置**（既定マスターと軸の上限。SCP の 900 マスターは上限
   の外）と **Monaspace の下限位置**（Monaspace の wght 200 のバーが
   SCP のバーと一致する SCP wght。これより細い側は Monaspace が下限で
   クランプされ一定、太い側は SCP 追随——このマスターが無いと Normal の
   記号が 4u 太くなる）を加えた 5 マスター——それぞれで SCP を厳密な wght に
   インスタンス化し、Monaspace を**太さ一致でインスタンス化**した静的
   マスターを用意する。マスターを置く設計座標は「SCP のユーザー wght を
   SCP 自身の fvar 正規化 + avar に通して線形化したもの」
   （`scp_design_axis`）——SCP の VF はユーザー wght に対して線形では
   ないので、ユーザー wght のまま線形補間すると中間ウェイトが静的版
   からずれる（初版はこれで Light のバーが 41u → 58u になっていた）。
   SCP 側のマスターは instancer の整数丸めを切ってインスタンス化する
   ——相対座標への丸めが経路に沿って累積し、丸めたマスターから組むと
   マスター間で `m` が最大 10u ずれた（実測）。
   Monaspace の wght 下限 200 で足りない場合、事前の見積りは「現行の
   erosion で削る」だったが、実装では **erosion をしない**方針にした
   ——erosion は pathops のブーリアン演算で非線形、マスター間の補間に
   使えるものではない（実測: `VFSource.matched` に `erode=False` を
   足すとそのまま下限でクランプするだけで済み、`fontTools.varLib.build`
   が問題なく通ることを確認済み）。詳細は次項のリスク参照
2. ✅ fontTools varLib でマスター群から CFF2 VF を組む（Upright /
   Italic は SCP と同じく別ファイル）。Monaspace 由来グリフは
   Monaspace VF の補間互換アウトラインから来るので互換性は保てるが、
   pathops の simplify を通すと点数が変わるため、**simplify は VF
   では使わず**重なりは残す（Adobe の VF と同じ扱い。
   `build.draw_clean` に `simplify=False` を追加）。ヒント付け・
   サブルーチン化も VF には行わない
3. ✅ STAT / fvar のインスタンス名は段階 1 と同じ 6 ウェイト、wght 軸は
   静的版の STAT と同じ usWeightClass の値（300/350/400/500/700/900、
   既定 400 = Regular で OS/2 usWeightClass と一致）で、avar が各値を
   段階 1 と同じ「SHCJ の `=` バー×600/667」に一致する SCP wght
   （実測: Upright 317/374/406/545/670/857、Italic 317/377/399/538/
   661/841）へ写す（`user_axis`。SCP 自身の avar の折れ点も引き戻して
   写像に含めるので、名前付きインスタンスの間でも SCP と厳密に一致
   する——`verify_latin_vf.py` が SCP_VF_U/I を指す環境で検証）。
   name テーブルは SCP VF 自身の慣習（`SourceCodeVF-Upright.otf` /
   `-Italic.otf`）に倣い nameID 6 に `SumiMoji-Roman` /
   `SumiMoji-Italic`、nameID 25 に `SumiMoji`、nameID 16/17 は省略
4. 未着手: JP 側 (`scripts/build.py`) を「欧文 VF をそのまま
   `VFSource.matched` でインスタンス化して使う」側へ切り替える作業。
   今回追加したのは Sumi Moji 単体の VF（配布物）のみで、JP 側は
   引き続き `dist/latin` の静的 OTF（`build_latin.py` の出力）を
   接ぎ木している
5. 未着手: JP 側 12 面を、今回の VF からインスタンス化して作る経路
   （今は `build_latin.py` が別レシピで静的 12 面を直接組んでいる）

見積りどおり数日で実装。4・5 は次の課題として残す。

## 6. リスク・未決事項

- **重なり除去 vs 補間互換**: 静的版では pathops で重なりを除去しているが、
  VF ではマスター間の点対応が崩れる。VF は重なりを残し、静的インスタンスで
  除去する二本立てにした（実装済み）
- **Light の削り**: erosion は非線形なので VF では補間で再現できない
  ——見積り時点では「Light 相当をマスターに立てる」を想定していたが、
  実装では **erosion 自体をしない**（Monaspace が自身の wght 200 の
  下限で単にクランプする）方針にした。SCP wght がおよそ 366 を下回ると
  Monaspace 側の記号・合字はその下限の太さで止まり、静的版が erosion
  で削っている太さより太くなる——Light（SCP wght ≈317）はこの範囲に
  入るため、VF の Light 相当の記号は静的 Light（erosion 版）よりわずかに
  太い。静的 Light は引き続き erosion 版を配布する。マスターを増やして
  この範囲もカバーする案は保留（erosion 自体が非線形なので、マスターを
  増やしても補間では再現できないことに変わりはない）
- **太さの線形性**: SHCJ の各面に対する wght の一致点は二分探索で求めている。
  SCP 側は設計座標を SCP の avar で線形化してあるので中間ウェイトでも
  厳密に一致する（実装済み、`verify_latin_vf.py` で検証）。Monaspace 側は
  5 マスターの間で線形補間になるため、名前付きインスタンスの間では
  SCP との太さ一致に 1u 程度のずれが出うる。超える場合はマスターを増やす
  ——実測では Regular 実インスタンスのバー厚が静的版に対し ±1u 以内
  （`scripts/verify_latin_vf.py` で継続確認）
- **Italic**: SCP Italic は −12°、Monaspace の slnt は −11° が下限。
  残り 1° のシアーは現行どおりマスター生成時に掛ける
- **名前**: Sumi Moji / Sumi Moji JP で確定。商標（USPTO / J-PlatPat）は
  この環境から未確認。変更箇所の一覧は 2 節
- **バージョン**: JP と同じタグで同時にリリースする（別バージョン番号を
  持たない）
