# Shoyu Code Pro JP

Source Han Code JP の思想を最新の上流で組み直したプログラミングフォント。
[Source Han Sans](https://github.com/adobe-fonts/source-han-sans)（和文）+
[Source Code Pro](https://github.com/adobe-fonts/source-code-pro)（欧文、10/9 拡大で 667 幅 —
Adobe が SHCJ を作った手順の再実行）+
[Monaspace](https://github.com/githubnext/monaspace)（合字50種）を
CI で合成し、上流の新リリースにも追従する。

ウェイトの対応付けは名前ではなく実測 — 各面で `=` のバー厚を測り、
SCP / Monaspace のバリアブルフォントの wght を二分探索で一致させる。
基準は [Source Han Code JP](https://github.com/adobe-fonts/source-han-code-jp)
（ペアリング参照、行間メトリクス、SCP 非収録の半角カナ等のドナー）なので、
SHCJ ユーザーの見た目の連続性が保たれる。

## 合字一覧

**Monaspace 由来の61種**を収録（[githubnext/monaspace](https://github.com/githubnext/monaspace) v1.400、OFL）。
主要どころ: `!=` `==` `===` `!==` `<=` `>=` `->` `<-` `=>` `~>` `:=` `::`
`<<=` `>>=` `=<<` `|>` `<|` `<>` `</>` `//` `#[` `...` `&=` `||` `!~` `=~`
`~~>` `<!--` `&&=` ほか（全61種）。全リストは `data/mona_ligs.json` を参照。

移植するのは合字グリフと、単独の ASCII 記号 32字全部
（`` !"#$%&'()*+,-./:;<=>?@[\]^_`{|}~ ``）。英数字やそれ以外の文字は
SHCJ（= Source Code Pro）のまま。SHCJ に無い SCP の約 600 字（`ł` `ğ` `ş`
`ı` `ř` `₽` などポーランド語・トルコ語・チェコ語等の文字）も SCP から
半角で取り込み、SHCJ に無く SHS が比例幅で持っていた `ς` `⁴` などは SCP の
半角版に差し替える。SHCJ が全角に割り当てている `→` `①` などはその方針を
維持し、SHS 側のグリフが比例幅のもの（`−` `ˇ` `˙`）は SHCJ の全角グリフを
写してグリッドに乗せる。

記号を丸ごと Monaspace に揃えたのは、合字自体が Monaspace 製である以上、
同じ記号が単独字と合字とで違う骨格を持つと隣り合わせたときに継ぎ目が
見えてしまうため（`#` と `#[`、`-` と `->`、`/` と `//` など）。最初に
移した `=` `<` `>` `|` `~` は形そのものが合字と違っていた（`=` と `==` で
バーの間隔が SCP 170u / Monaspace 219u、`<` と `<=` で大きさと角度、`|` と
`||` で上下の伸び、`~` と `~>` で振幅）。残りの記号はおおむね縦のサイズ
違いで、Monaspace の cap 高・x-height が SCP より高いぶん `!` `&` `?` `:`
`;` は 16〜67u 持ち上がり、括弧類や `#` `@` `$` は 60〜150u 高く最大 96u
幅も広い — いずれもセル内に収まり、ターミナルサイズでは2ピクセル未満の
差。`-` は `=` より 124u 短いが、これは Monaspace 自身がそういう字形の
ため。SCP の `cv14`/`cv15`/`cv16`（タイポグラフィックなハイフン・
アスタリスク・スラッシュ付きドル記号）を有効にすると、`-` `*` `$` は
SCP の字形に戻る。

線の太さは**面ごとに** SHCJ の `=` のバー厚を実測し、Monaspace VF の wght を
二分探索で一致させたインスタンスから取り込む。Italic 面には slnt 軸で傾斜も
追随させ（SCP Italic の −12° に対し Monaspace の slnt は −11° が下限なので、
残り 1° はアウトラインをシアーして合わせる）、ベースラインは両フォントの
`=` の縦中心を揃える。
GSUB は `calt` / `liga` 両登録（全合字が既定で有効）。加えて Monaspace 流の
**グループ別 stylistic set** を備え、`calt` を切って必要な群だけ有効化できる:

| feature | 内容 | 例 |
|---------|------|----|
| ss01 | 比較・等価 | `!=` `===` `<=` `>=` `!~` `=~` |
| ss02 | 矢印 | `->` `<-` `=>` `>>=` `~~>` |
| ss03 | マークアップ | `</` `/>` `</>` `<>` `<!--` |
| ss04 | パイプ | `\|>` `<\|` |
| ss05 | コロン | `::` `:=` `:>` `<:` |
| ss06 | ドット | `..` `...` `..<` `.=` |
| ss07 | コメント | `//` `///` |
| ss08 | 反復・論理・その他 | `\|\|` `<<` `>>` `#[` `#(` `&=` `&&` `&&=` `++` |
| ss09 | 幅の代替（矢印・≠≤≥…の 1 セル版） | |
| cv99 | 演算子の代替デザイン（Monaspace の .alt） | |

さらに **Source Code Pro 自身の字形バリアントを貫通**させている:
`zero`（スラッシュゼロ切替）、`cv01`〜`cv17`（`a` の一階建て、`g` の形など
SCP 純正の文字変異）、`salt`、SCP の stylistic set は ss11〜ss17 に +10 で
マウント（ss01〜ss08 は合字グループが使用）。行間は SHCJ の宣言値を複写。

```jsonc
// 例: !== の一体化が読みにくい場合、比較系だけ切って矢印は残す
"editor.fontLigatures": "'calt' off, 'ss02', 'ss03', 'ss05', 'ss06', 'ss07', 'ss08'"
```
ss01〜08 はグループごとに別のルックアップなので、`calt` を切ったまま複数
グループを同時に有効にすると、片方の短い列（ss01 の `>=`）がもう片方の
長い列（ss02 の `>>=`）の頭を食ってしまうことがある。Monaspace 本家の
stylistic set も同じ挙動なので許容している。グループを跨いだ安全性が
欲しい場合は `calt` を使うこと。

`:=` と `::` は Monaspace 内でも文脈変異（`colon.case`）で実現されているため、
同グリフの合成として取り込んでいる（実レンダリングと誤差1ユニット未満で一致）。
同じ手法で `&&` `++`（`&` `+` の init/fina 変異）、`..<` `.=`（ピリオドを
上げた変異）、`:>` `<:`（コロンを上げた変異）も合成して取り込んでいる。

## ファミリー構成

| ファミリー | 半角:全角 | `=`バー | 用途 |
|-----------|-----------|--------|------|
| Shoyu Code Pro JP | 667:1000 (2:3) | 69 | エディタ用（SHCJ の見た目） |
| Shoyu Code Pro JP Term | 600:1200 (1:2) | 69 | ターミナル用 |
| Shoyu Code Pro JP 35 | 600:1000 (3:5) | 62 | SCP 原寸・原太（本家忠実） |

`=`バーの値は現在ピン留めしている上流タグでの実測値（目安）。上流が
更新されビルドし直すと、各面の太さマッチングの結果として多少前後しうる。

**Term** は発想を逆にした 1:2: 欧文を縮めず、**全角の送りを 1200
（=600×2）に広げてグリフを中央配置**する。欧文は SCP 原寸（600）に
太さ補正（SHCJ の CJK ペアリング 69/1000em に一致）を掛けたもの。
ターミナルのセルグリッドに厳密一致し罫線も繋がる。曖昧幅（EAW=A）の
記号は HackGen Console / PlemolJP Console / Moralerspace HW と同じ整理:
合字と対になる `←` `→` `↑` `↓` `⇐` `⇒` `⇔` `≠` `≤` `≥` `…` は **Monaspace の
半角グリフ**（`<-` `!=` `<=` `...` と同じ太さ・矢尻）、SCP が持つ `×` `÷` `■`
ギリシャ文字・アクセント付きラテン・キリル文字・罫線素片は **SCP 自身の
半角グリフ**（1セル。罫線は上下に食み出す設計なので行間に関わらず繋がる）、
どちらにも無い `①` `※` などは**全角のまま**（縮めない）。曖昧幅を
半角扱いするターミナルでは `①` が右隣に食み出すが、これは HackGen と同じ
挙動で、Windows Terminal なら `"compatibility.ambiguousWidth": "wide"`、
iTerm2 / WezTerm なら相当の設定で 2 セル取らせれば JP と同じ大きさで出る。

矢印7種（`←` `→` `↑` `↓` `⇐` `⇒` `⇔`）は JP / 35 でも全角のまま（SHCJ の
幅・インク量を維持）だが、**合字グリフそのものから切り出している**。
`→` `←` は `->` `<-`、`⇒` は `=>`、`⇐` はその鏡像、`⇔` は `<=>`、`↑` `↓` は
`->` を 90° 回転したものを元に、軸の途中を詰めるか伸ばすかして Source
Han Sans のインク長に合わせる（横矢印は x 方向、縦矢印は y 方向、Italic
では傾斜を抜いてから加工して後で掛け直す）。Monaspace 自身の `→` 文字は
`->` より矢尻が小さく縦位置も違うため、それを伸ばしても揃わない。
`≠` `≤` `≥` `…` は軸がないので JP / 35 では既定どおり Source Han Sans の
全角グリフのまま。フォントは接続先のターミナルの曖昧幅設定を検知できないため、
この11字（矢印7種 + `≠` `≤` `≥` `…`）はどのファミリーでも両方の字形を
持たせたうえで OpenType feature で手動切り替えする形にしている:

| ファミリー | 既定 | `hwid` | `fwid` | `ss09` |
|-----------|------|--------|--------|--------|
| JP / 35 | 全角（Source Han Sans） | 半角（Monaspace 1セル） | — | 半角（Monaspace 1セル） |
| Term | 半角（Monaspace 1セル） | — | 全角（Source Han Sans、2セル） | — |

`hwid` / `fwid` は Source Han Sans 由来の既存 feature なので、有効にすると
SHS 自身の半角カナ・半角記号も一緒に切り替わる。この11字だけを動かしたい
場合は `ss09` を使う（JP / 35 のみ；Term は既定がすでに半角なので `fwid`
で全角に戻す）。

```jsonc
// VS Code で JP / 35 の矢印・≠≤≥… だけ半角にする
"editor.fontLigatures": "'ss09'"
```

```jsonc
// Windows Terminal のフォント feature 設定
{ "ss09": 1 }
```

HackGen Console / PlemolJP Console / Moralerspace HW / UDEV Gothic JPDOC
など他の合成型日本語プログラミングフォントはこの調整のために別ファミリー
（Console / HW / JPDOC 系）を用意しているが、本フォントでは各ファミリー
内の feature 切り替えとして持たせている。

35 の太さ補正版（35W、バー69）も試作したが、実用サイズ（14px）で
知覚できない差だったため引退。Term は全角と常時並ぶ前提なので
理論的に正しい補正済みの値を採っている。

かつて 1:2 の Console 変種を作ったが引退させた。SCP のゆったりした骨格を
500 セルに収めるには等方縮小（欧文が25%小さく細い）か約17%のコンデンス化
（線コントラストも歪む）しかなく、実際に両方ビルドして目視評価した結果、
どちらも SCP の字形を名乗るには失うものが多すぎた。1:2 が必要なら Iosevka
系（Sarasa）のような細身設計の欧文を使うフォントが素直（機構は
`rescale(ky=)` / `narrow_ambiguous()` として残してある）。

各ファミリー 6ウェイト（Light / Normal / Regular / Medium / Bold / Heavy）× 2スタイル
（Upright / Italic — Italic は SCP の本物の
イタリック、和文は SHCJ と同じく直立のまま）。Monaspace VF の wght 下限（200）は
`=` バー厚 59u で SHCJ Light の 47u に届かないため、Light では Monaspace 由来の
アウトラインを片側 6u 内側に削って（pathops でストローク幅 2d を差し引く）
太さを合わせている。SHCJ の ExtraLight（31u）は片側 14u 削る必要があり
`:=` `...` の点が痩せすぎるので作らない。

35 は半角グリフを 600/667 に等方縮小したもの（= オリジナル SCP の原寸復元）。
半角カナ（`ｱ` `｡` `｢` など）は SHCJ が 500 幅（1000 の半分）で持っていて 667 にも
600 にも乗らないため、35 / Term では 600 セルに中央配置してグリッドに乗せる
（2:3 の JP は SHCJ の見た目を優先してそのまま）。全出力に Nerd Fonts
パッチ済み変種も生成する。NF ファミリー名は日本語プログラミングフォントの
慣習（HackGen / PlemolJP / UDEV Gothic と同じ）に合わせ**変種名の後ろ**に付く:
`Shoyu Code Pro JP NF` / `Shoyu Code Pro JP Term NF` / `Shoyu Code Pro JP 35 NF`。CID-keyed CFF のままでは
font-patcher がグリフを Unicode で引けないため、パッチ前に FontForge の
`cidFlatten()` で平坦化している（アウトラインは無変換）。

## Sumi Moji（欧文のみ、仮称）

Shoyu Code Pro JP が使う欧文レイヤーを、VF から直接組み上げた和文なしの
単独フォント。JP 側（`build.py`）はこのフォントを Source Han Sans に
接ぎ木するだけになっており、欧文の設計判断は 1 か所に集まっている。

ベースは Source Han Code JP の `=` バーに合わせた Source Code Pro VF の
インスタンスを、fontTools の CFF2ToCFF で静的な CID-keyed CFF に変換した
もの——SCP 自身のアウトライン・アライメントゾーン・GSUB（`cv01`〜`cv17`
`zero` `salt`、SCP の stylistic set は `ss11`〜`ss17` に移動）・GPOS
（マーク位置決め）はそのまま生きている。インスタンス化でヒントは失われる
ため、SCP 自身のゾーンに対して otfautohint で全体を再ヒント。その上に
Monaspace 由来の合字61種・ASCII 記号32字・1セル矢印（SCP に無い `⇔` も
追加）を、太さとベースラインを揃えて接ぎ木し、cffsubr でサブルーチン化
する。結合文字は SCP が出荷する形（スペーシング、GPOS mark で位置決め）
のまま。

2つのプロファイルが同じレシピから出る: `dist/latin/`（配布される Sumi
Moji 本体。バー = SHCJ のバー × 600/667、35 と同じ太さ）と
`dist/latin/term/`（Term ファミリー専用の内部ドナー。バー = SHCJ のバー
そのまま 600 セルで——Term は欧文を縮めないぶん太めに対応させる必要が
ある。配布はしない）。

Regular は1,632グリフ・約140KB（Italic は1,335グリフ — SCP Italic VF の
グリフ数が少ないぶん）。縦メトリクスは SCP 自身の hhea（984 / -273）を
基準に、OS/2 の typo を hhea と同値にして `USE_TYPO_METRICS` を立て、win
はファミリー全面のバウンディングボックスを覆う値（Regular ペアで
1060 / 454）。

```sh
python scripts/build_latin.py  # SCP VF + Monaspace VF -> dist/latin{,/term}/SumiMoji*-*.otf
python scripts/build.py        # dist/latin を Source Han Sans に接ぎ木
```

`build_latin.py` には `SCP_VF_U` / `SCP_VF_I` / `MONA_VF` / `SHCJ_TTC` が
必要（`build.py` と同じ変数）。先に走らせて `dist/latin` を作ってから
`build.py` を実行する（CI・リリースとも同じ順序）。

**Sumi Moji VF（可変フォント）**: `scripts/build_latin_vf.py` は同じ
レシピを CFF2 可変フォントとして組む——`dist/latin/SumiMoji[wght].otf`
（Upright）と `dist/latin/SumiMoji-Italic[wght].otf`（Italic）。wght 軸は
静的版の STAT と同じ usWeightClass の値で切ってある——300 / 350 / 400 /
500 / 700 / 900 = Light / Normal / Regular / Medium / Bold / Heavy、既定値
400 = Regular（軸を指定せずに VF を選んでも Regular が出る。OS/2 の
usWeightClass 400 と一致し、CSS の `font-weight: 700` は Sumi Moji の
Bold に落ちる）。各値は avar で「SHCJ の `=` バー × 600/667 に一致する
SCP wght」（実測: Upright 317/374/406/546/669/857、Italic 317/378/399/
538/662/841）へ写され、その間は SCP 自身の avar の折れ点も通して
補間する——SCP の VF はユーザー wght に対して線形ではない（avar で
曲げてある）ので、これを引き継がないと中間ウェイトが静的版と一致し
ない。マスターは SCP VF 自身のマスター位置（wght 200 / 400——CFF2 の
VarStore から実測、決め打ちしない）に Regular と Heavy の位置（Regular
が既定マスター、Heavy が軸の上限。SCP の 900 マスターは上限の外なので
使わず、SCP が 400〜900 で線形なことを利用して Heavy 位置でインスタンス
化する）と Monaspace の下限位置（Monaspace の wght 200 のバーが SCP の
バーと一致する SCP wght——これより細い側では Monaspace が下限でクランプ
されるので、ここにマスターを置くと下限側は一定・上限側は SCP 追随になる）
を加えた 5 つで、各マスターで Monaspace を太さ一致でインスタンス化する。
SCP 側のマスターは fontTools の instancer の整数丸めを切ってインスタンス化
する（charstring の相対座標に丸めが累積して、マスター間で `m` などが
数 u ずれるのを避けるため。VF は CFF2 の固定小数精度でそのまま持てる）。ただし重なり除去（`pathops.simplify`）とヒント付け・サブルーチン
化はしない——重なりは Adobe が SCP 自身の VF でしているのと同じ扱いで
残し（マスター間で点の対応が壊れるため）、ヒントはインスタンス化で
失われるので配布用の静的インスタンスを別途作る側の仕事のままにする。

wght 軸の範囲は 200〜900。ただし SCP wght がおよそ 366 を下回ると
（ユーザー wght でおよそ 340 未満）、Monaspace 側の記号・合字は自身の
wght 200 の下限（＝静的版が erosion で削っている太さ）より薄くできない
——erosion は pathops の非線形なブーリアン演算で、マスター間の補間では
再現できないため VF のマスターには使えない。したがって VF の軽量側
（Light 相当）では記号・合字だけが下限の太さで止まり、erosion 済みの
静的 Light より心持ち太くなる。静的 Light は引き続き erosion 版を配布する。

「Sumi Moji」はまだ仮称（PostScript 名は `SumiMoji-*`）。経緯・命名調査・
今後の計画は [docs/sumi-moji-plan.md](docs/sumi-moji-plan.md) を参照。

## インストール

[Releases](../../releases) から用途に応じてアセットを選ぶ。いずれの zip にも
OFL のライセンス全文（LICENSE）を同梱している。

- **`ShoyuCodeProJP.zip`**: 面ごとに分かれた個別の OTF。必要な面だけ
  入れたい人向け。
- **`ShoyuCodeProJP.ttc` / `ShoyuCodeProJP35.ttc` / `ShoyuCodeProJPTerm.ttc`**:
  各ファミリー12面（6ウェイト×2スタイル）を1ファイルにまとめた TTC。
  1ファイルで全面をインストールできる（サイズは OTF 合計と3%しか
  違わないので、選ぶ利点はもっぱらインストールの手間が減ること）。
- **`ShoyuCodeProJP-NerdFont.zip`**: Nerd Fonts のアイコングリフを追加した
  NF 変種（ファミリー名は末尾に `NF` が付く、例 `Shoyu Code Pro JP NF`）。
  ターミナルのプロンプト装飾（アイコン表示）に使う場合はこちら。
- **`SumiMoji.zip`**: 和文を含まない欧文のみの Sumi Moji（仮称）12面。
  NF 変種と TTC はまだ無い。

ダウンロードしてインストールし、

```jsonc
{
  "editor.fontFamily": "Shoyu Code Pro JP",
  "editor.fontLigatures": true
}
```

ファミリー名を `Shoyu Code Pro JP` にリネームしてあるので、
オリジナルと共存できる。

- **macOS**: OTF をダブルクリックして「フォントブック」でインストール、または
  `~/Library/Fonts/` にコピー。
- **Windows**: OTF を右クリックして「インストール」を選択（全ユーザー適用は
  「すべてのユーザー用にインストール」）。
- **Linux**: `~/.local/share/fonts/`（ユーザー単位）または
  `/usr/local/share/fonts/`（全ユーザー）にコピーし、`fc-cache -f` を実行。

ビルドやリガチャの追加・改造に興味がある場合は [CONTRIBUTING.md](CONTRIBUTING.md) を参照。

## ビルド

4つの上流（Source Han Sans JP / Source Code Pro VF / Monaspace VF /
Source Han Code JP）を取得して環境変数で場所を渡す。ビルドは2段階:
まず `scripts/build_latin.py` が VF から Sumi Moji（`dist/latin`）を
組み、その完成品を `scripts/build.py` が Source Han Sans に接ぎ木する。
具体的なコマンドは `.github/workflows/ci.yml` の手順がそのまま実行可能な
リファレンス。

```sh
pip install -r requirements.txt
SCP_VF_U=... SCP_VF_I=... MONA_VF=... SHCJ_TTC=upstream/SourceHanCodeJP.ttc \
  python scripts/build_latin.py           # dist/latin{,/term}/SumiMoji*-*.otf
SHS_DIR=... SHCJ_TTC=upstream/SourceHanCodeJP.ttc \
  python scripts/build.py                 # 全ファミリー（2:3 / 35 / Term × 12面）
  python scripts/build.py "Regular"       # Regular系のみ（動作確認用）
python scripts/verify.py dist/ShoyuCodeProJP-Regular.otf   # 回帰テスト
python scripts/nerdpatch.py <FontPatcher dir>              # NF 変種
python scripts/makeotc.py                                  # .ttc 化
```

`SHCJ_TTC` は [Source Han Code JP の GitHub Releases](https://github.com/adobe-fonts/source-han-code-jp/releases)
から `SourceHanCodeJP.ttc` をダウンロードして指すパス（`.github/workflows/ci.yml`
と同じ取得元・同じ手順、`build_latin.py` / `build.py` 共通）。
`SCP_VF_U` / `SCP_VF_I` / `MONA_VF` は `build_latin.py` だけが使い、
それぞれ Source Code Pro VF / Monaspace VF の Releases から取得する。
`build.py` は Source Code Pro / Monaspace の VF に直接触らず、代わりに
`SHS_DIR`（Source Han Sans JP）と `LATIN_DIR`（既定 `dist/latin`、
`build_latin.py` の出力先）を見る。

`requirements.txt` には AFDKO（`otfautohint` でグラフト・拡幅したグリフに
ヒントを付ける）も含まれる。ローカルでの試しビルドで時間を節約したい場合は
`SHOYU_SKIP_AUTOHINT=1` を立てるとスキップできる。ヒント付与後は
cffsubr（AFDKO の `tx`、`requirements.txt` に同梱）で CFF をサブルーチン化
している。ビルドが生成する charstring はすべてフラットで、Term は全角
グリフ約1.7万個を丸ごと再生成するため、ヒントを付けただけの Term 面は
44%肥大（6.7MB）していた。サブルーチン化後は4.6MB — ヒントを保ったまま
v3.2.0（4.66MB）より小さい。

## 仕組み

- 欧文レイヤーは Sumi Moji（`scripts/build_latin.py`、VF から先に組んで
  `dist/latin` に出力）から来る。Source Han Sans JP（CID-keyed CFF）を
  土台に、SHCJ が半角にしている 477 コードポイントへ Sumi Moji 由来の
  グリフを接ぎ木し cmap を差し替える（Sumi Moji に無い半角カナ等は
  SHCJ から複写）。追加 CID は疎な空間の空きを昇順割当（サブセット OTF
  の CID は不連続なため）
- 太さの一致は Sumi Moji 側（`build_latin.py`）で完結している——各面の
  `=` バー厚を実測して SCP / Monaspace VF の wght を二分探索で合わせ、
  Italic は SCP Italic VF + slnt 追随。`build.py` は Sumi Moji を
  667/600 セルへ再スケールするだけ（Term は内部専用の Term プロファイル
  を使う）
- 合字は LigatureSubst。`calt`/`liga` は結合ルックアップ1つ＋文脈ガード
  （各合字の入力列全体をカバーするトリガールールを最長一致順に並べる。
  一致範囲を1文字だけにしてネストした LigatureSubst に残りを委ねる形は
  一致範囲外の消費が OpenType 未定義動作で DirectWrite が非対応だった
  ため）、ss01〜08 はグループ別ルックアップ、cv99 が .alt 切替
- 行間は SHCJ の宣言値を複写。等幅メタデータ（`post.isFixedPitch` /
  PANOSE bProportion=9 / xAvgCharWidth）は各面で独自に設定・実測し、
  Windows Terminal 等のフォント選択に出るようにする
- 欧文・合字・（Term では）拡幅した全角グリフなど T2CharStringPen で
  描いたグリフは、最終アウトラインで測ったアライメントゾーン付きの
  専用 CID FontDict を割り当てたうえで AFDKO の otfautohint によりヒント
  を付与（Source Han Sans 由来のグリフは元のヒントのまま）

## ライセンス

フォント本体は上流と同じ [SIL OFL 1.1](https://github.com/adobe-fonts/source-han-code-jp/blob/master/LICENSE.txt)。
OFL の Reserved Font Name 規定に基づき、ファミリー名は変更済み（Source→Shoyu、nerd-fonts の SauceCodePro と同じ流儀の言い換え）。
