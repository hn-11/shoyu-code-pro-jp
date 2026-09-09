# Sumi Moji JP

英語圏のターミナルフォントの流儀で組んだ、日本語入りのプログラミング
フォント。欧文は [Source Code Pro](https://github.com/adobe-fonts/source-code-pro)
（原寸・原太、名前付きインスタンスそのまま）に
[Monaspace](https://github.com/githubnext/monaspace) の記号と合字 61 種を
載せた **Sumi Moji**、和文は [Source Han Sans](https://github.com/adobe-fonts/source-han-sans)
JP を、Sumi Moji の太さに合う面から取る。基準は欧文側で、セル幅（600）、
ウェイト（Light / Regular / Medium / SemiBold / Bold）、行間
（984 / −273 = 1.257 em）はすべて Source Code Pro のもの。和文がそれに
従う。CI で合成し、上流の新リリースにも追従する。

## ファミリー構成

| ファミリー | 半角:全角 | 用途 |
|-----------|-----------|------|
| Sumi Moji JP | 600:1000 (3:5) | エディタ。和文は Source Han Sans の送りのまま |
| Sumi Moji JP Term | 600:1200 (1:2) | ターミナルのグリッドに乗せたい非グリッドのアプリ向け。全角の送りを 2 セルに広げてグリフを中央配置 |
| Sumi Moji | 600 | 欧文のみ（可変フォント） |

ターミナルの中では JP と Term は同じに描かれる（全角は 2 セルに置かれる）。
違うのは全角の送り幅だけで、Latin・記号・幅の方針は共通。

各ファミリー 5 ウェイト × 2 スタイル（Upright / Italic。Italic は Source
Code Pro の本物のイタリック、和文は直立のまま）。ウェイトは Source Code
Pro の名前付きインスタンスで、和文は `=` のバー厚が合う Source Han Sans
の面を実測で選ぶ:

| ウェイト | usWeightClass | Source Code Pro の `=` バー | Source Han Sans の面（`＝` バー） |
|---------|---------------|-----------------------------|-----------------------------------|
| Light | 300 | 37u | ExtraLight（36u） |
| Regular | 400 | 62u | Normal（63u） |
| Medium | 500 | 73u | Regular（69u） |
| SemiBold | 600 | 83u | Medium（83u） |
| Bold | 700 | 104u | Bold（101u） |

Source Han Sans の Light（49u）と Heavy（120u）、Source Code Pro の
ExtraLight（28u）と Black（120u）は相手がいないので作らない。

## 幅の方針

**Sumi Moji が持つ文字はすべて 1 セル**。Latin、ギリシャ、キリル、
アクセント付き文字、罫線素片、`←` `→` `↑` `↓` `⇐` `⇒` `⇔` `≠` `≤` `≥` `…`
も 1 セルで、英語のターミナルフォントと同じ。Source Han Sans にしかない
文字（漢字・かな・`①` `※` など）は Source Han Sans の全角のまま。Source
Han Sans が比例幅で持つ半角カナ（500）や Hangul 字母（920）などは、
その送り幅がいちばん近いグリッド（セルか全角の倍数）に中央配置する。
Source Han Sans のギリシャ文字は 602〜795、`Ю` は 1005〜1064 と、
セルや全角を少し超える幅で描かれているので、切り上げるとそれぞれ
ターミナル 1 桁分を余計に取ってしまう（しかもウェイトによって
1 桁だったり 2 桁だったりする）。斜体は Source Code Pro Italic に
ギリシャ・キリルが無いぶん、この規則が効いて欧文の直立と同じ 1 セルに
なる。

例外は、両ドナーが 1 セル幅で描いていて Unicode の東アジア文字幅が
Wide の 13 字（`☕` `🎵` `🎶` `💩` `🔒` `🤖` と Hangul 声調記号 2 字、
注音の入声 5 字）。ターミナルは 2 桁分を空けるので左寄りに見える。
Source Code Pro / Source Han Sans にこれより広い字形が無いため、
`fwid` の代替も用意していない。

JIS 流の全角字形は `fwid` で戻せる。矢印 7 種は合字グリフ（`->` `=>`
`<=>` の鏡像・回転）から Source Han Sans のインク長に合わせて切り出した
全角版、`≠` `≤` `≥` `…` や罫線は Source Han Sans 自身の全角グリフ、`A`
など Source Han Sans が `fwid` の形を持つ文字はその形（`Ａ`）。

```jsonc
// VS Code で矢印や罫線を全角に
"editor.fontLigatures": "'fwid'"
```

幅を動かす機能は入れていない。Source Han Sans の `kern`（横組みでは
既定 ON。`あ`+`て` をセルより 20u 詰める）、`halt`、縦組みの GPOS は
ビルド時に落としてある。

曖昧幅（EAW=A）を 2 セルとして数えるターミナルでは `①` が右隣に食み出す。
これは HackGen と同じ挙動で、Windows Terminal なら
`"compatibility.ambiguousWidth": "wide"`、iTerm2 / WezTerm なら相当の設定で
2 セル取らせる。

## 合字一覧

**Monaspace 由来の61種**を収録（[githubnext/monaspace](https://github.com/githubnext/monaspace) v1.400、OFL）。
主要どころ: `!=` `==` `===` `!==` `<=` `>=` `->` `<-` `=>` `~>` `:=` `::`
`<<=` `>>=` `=<<` `|>` `<|` `<>` `</>` `//` `#[` `...` `&=` `||` `!~` `=~`
`~~>` `<!--` `&&=` ほか（全61種）。全リストは `data/mona_ligs.json` を参照。

移植するのは合字グリフと、単独の ASCII 記号 32字全部
（`` !"#$%&'()*+,-./:;<=>?@[\]^_`{|}~ ``）。英数字やそれ以外の文字は
Source Code Pro のまま。

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

線の太さは**面ごとに** Source Code Pro のインスタンスの `=` のバー厚を
実測し、Monaspace VF の wght を二分探索で一致させたインスタンスから
取り込む。Italic 面には slnt 軸で傾斜も追随させ（SCP Italic の −12° に
対し Monaspace の slnt は −11° が下限なので、残り 1° はアウトラインを
シアーして合わせる）、ベースラインは両フォントの `=` の縦中心を揃える。
Monaspace VF の wght 下限（200）は `=` バー厚 53u で SCP Light の 37u に
届かないため、Light では Monaspace 由来のアウトラインを片側 8u 内側に
削って（pathops でストローク幅 2d を差し引く）太さを合わせている。
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
| cv99 | 演算子の代替デザイン（Monaspace の .alt） | |

さらに **Source Code Pro 自身の字形バリアントを貫通**させている:
`zero`（スラッシュゼロ切替）、`cv01`〜`cv17`（`a` の一階建て、`g` の形など
SCP 純正の文字変異）、`salt`、SCP の stylistic set は ss11〜ss17 に +10 で
マウント（ss01〜ss08 は合字グループが使用）。

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

## Nerd Fonts 版

全面に Nerd Fonts のアイコングリフを追加した変種も生成する。アイコンは
1 セルに収めるので、Nerd Fonts 本家の命名では **Mono** に当たり、
ファミリー名は `Sumi Moji JP Nerd Font Mono` / `Sumi Moji JP Term Nerd
Font Mono` / `Sumi Moji Nerd Font Mono`（PostScript 名 `SumiMojiJPNFM-*`
など。`JetBrainsMono Nerd Font Mono` と同じ流儀）。

アイコンは font-patcher で掛けるのではなく、Nerd Fonts が配っている記号
だけのフォント `Symbols Nerd Font Mono`（各リリースの
NerdFontsSymbolsOnly.zip。font-patcher の全記号集合と群ごとの寸法を空の
フォントに適用したもの）から fontTools で接ぎ木する。`--complete --mono`
でパッチしたのと同じ記号・同じ相対寸法になり、FontForge の往復（CID 構造
の平坦化、STAT の消失、メタデータの復元）が要らず、1 面 10 秒程度。
寸法は font-patcher 自身の群ごとの規則に合わせる（`icon_transform`）。

| 群 | font-patcher の指定 | 寸法 |
| --- | --- | --- |
| 通常のアイコン | `pa` | セル幅 / 記号フォントの em（600 / 2048）で一律。行ボックスの中央に置く |
| Powerline の区切り（`SEPARATORS`） | `^xy` | インクをセル幅と行の全高いっぱいに引き伸ばす。記号フォントが付けている食み出し（font-patcher の `overlap`）は比率のまま残す |
| Powerline のその他（`` `` ブランチ・鍵・行番号など） | `^pa` | 縦横比を保ったまま行の全高いっぱいに |

記号フォント自体は正方形のセル（2048 × 2048）向けなので、区切りは
font-patcher の `xy-ratio`（0.7 など）で頭打ちになった幅（2048 中 1447）
しか持たない。こちらのセルは 600 × 1257 と縦長で頭打ちに掛からないため、
インクはセルいっぱいに広がる。Source Code Pro 自身が持つ Powerline
（U+E0A0〜E0A2、E0B0〜E0B3）は記号フォントのもので置き換える。
アイコンはヒント無し（font-patcher の出力も同じ）。記号のライセンス（Nerd Fonts の MIT と各出典）は NF の zip に
`LICENSE-NerdFonts` として同梱する。

## Sumi Moji（欧文のみ）

Sumi Moji JP が使う欧文レイヤーを、VF から直接組み上げた和文なしの
単独フォント。JP 側（`build.py`）はこのフォントを Source Han Sans に
そのまま接ぎ木するだけになっており、欧文の設計判断は 1 か所に集まっている。

ベースは Source Code Pro VF の名前付きインスタンス（wght 300 / 400 / 500 /
600 / 700）を、fontTools の CFF2ToCFF で静的な CID-keyed CFF に変換した
もの——SCP 自身のアウトライン・アライメントゾーン・GSUB（`cv01`〜`cv17`
`zero` `salt`、SCP の stylistic set は `ss11`〜`ss17` に移動）・GPOS
（マーク位置決め）はそのまま生きている。インスタンス化でヒントは失われる
ため、SCP 自身のゾーンに対して otfautohint で全体を再ヒント。その上に
Monaspace 由来の合字61種・ASCII 記号32字・1セル矢印（SCP に無い `⇔` も
追加）を、太さとベースラインを揃えて接ぎ木し、cffsubr でサブルーチン化
する。結合文字は SCP が出荷する形（スペーシング、GPOS mark で位置決め）
のまま。

Regular は1,632グリフ・約140KB（Italic は1,335グリフ — SCP Italic VF の
グリフ数が少ないぶん）。縦メトリクスは SCP 自身の hhea（984 / -273）を
基準に、OS/2 の typo を hhea と同値にして `USE_TYPO_METRICS` を立て、win
はファミリー全面のバウンディングボックスを覆う値（1060 / 454）。

**可変フォント**: 配布する Sumi Moji は `scripts/build_latin_vf.py` が
同じレシピを CFF2 可変フォントとして組んだ `SumiMoji[wght].otf`
（Upright）と `SumiMoji-Italic[wght].otf`（Italic）。wght 軸は
usWeightClass の値で、名前付きインスタンスは静的面と同じ 300 / 400 /
500 / 600 / 700、既定値 400 = Regular。ユーザー wght は SCP の wght
そのもの（SCP のユーザー wght が usWeightClass）で、その間は SCP 自身の
avar の折れ点を通して補間する——SCP の VF はユーザー wght に対して線形
ではないので、これを引き継がないと中間ウェイトが SCP と一致しない。
マスターは SCP VF 自身のマスター位置（wght 200 / 400——CFF2 の VarStore
から実測）に Bold の位置（軸の上限。SCP の 900 マスターは上限の外なので
使わず、SCP が 400〜900 で線形なことを利用して Bold 位置でインスタンス化
する）と Monaspace の下限位置（Monaspace の wght 200 のバーが SCP の
バーと一致する SCP wght、およそ 365。これより細い側では Monaspace が
下限でクランプされる）を加えた 4 つ。SCP 側のマスターは fontTools の
instancer の整数丸めを切ってインスタンス化する。重なり除去とヒント付け・
サブルーチン化はしない（マスター間で点の対応が壊れるため。ヒントは
静的面の側で付ける）。軽量側では Monaspace 側の記号・合字が下限の太さで
止まるので、erosion 済みの静的 Light より心持ち太くなる。静的面は JP 面の
ドナーと Nerd Fonts 版の入力で、単体では配布しない。

名前の由来・衝突調査・欧文層を切り出した経緯は [docs/sumi-moji-plan.md](docs/sumi-moji-plan.md) を参照。

## インストール

[Releases](../../releases) から用途に応じてアセットを選ぶ。いずれの zip にも
OFL のライセンス全文（LICENSE）を同梱している。

- **`SumiMojiJP.zip` / `SumiMojiJPTerm.zip`**: ファミリーごとの zip
  （5 ウェイト × 2 スタイルの 10 面、面ごとの OTF）。使うファミリーだけ
  落として、必要な面だけ入れる（TTC は配らない: リリースの単位は
  インストールするファイルの単位）。
- **`SumiMojiJP-NerdFont.zip` / `SumiMojiJPTerm-NerdFont.zip`**: 同じ
  ファミリー分けの Nerd Fonts 版（ファミリー名 `Sumi Moji JP Nerd Font
  Mono` など）。ターミナルのプロンプト装飾（アイコン表示）に使う場合は
  こちら。
- **`SumiMoji.zip`**: 和文を含まない欧文のみの Sumi Moji。可変フォント
  2面（`SumiMoji[wght].otf` / `SumiMoji-Italic[wght].otf`）。
- **`SumiMoji-NerdFont.zip`**: Sumi Moji の Nerd Fonts 版（`Sumi Moji Nerd
  Font Mono`）。可変フォントには接ぎ木しないので、こちらは 5 ウェイト ×
  2 スタイルの静的 10 面。

ダウンロードしてインストールし、

```jsonc
{
  "editor.fontFamily": "Sumi Moji JP",
  "editor.fontLigatures": true
}
```

v4.0.0 までの Sumi Moji JP（2:3 の基本ファミリーと 35 / Term）や
v3.2.0 までの `Shoyu Code Pro JP` とはファミリー名が違うので共存する。
置き換えるなら旧版をアンインストールする。

- **macOS**: OTF をダブルクリックして「フォントブック」でインストール、または
  `~/Library/Fonts/` にコピー。
- **Windows**: OTF を右クリックして「インストール」を選択（全ユーザー適用は
  「すべてのユーザー用にインストール」）。
- **Linux**: `~/.local/share/fonts/`（ユーザー単位）または
  `/usr/local/share/fonts/`（全ユーザー）にコピーし、`fc-cache -f` を実行。

ビルドやリガチャの追加・改造に興味がある場合は [CONTRIBUTING.md](CONTRIBUTING.md) を参照。

## ビルド

3つの上流（Source Han Sans JP / Source Code Pro VF / Monaspace VF）と、
Nerd Fonts 版のための `Symbols Nerd Font Mono` を取得して環境変数で場所を
渡す。ビルドは2段階: まず `scripts/build_latin.py`
が VF から Sumi Moji（`dist/latin`）を組み、その完成品を `scripts/build.py`
が Source Han Sans に接ぎ木する。具体的なコマンドは
`.github/workflows/ci.yml` の手順がそのまま実行可能なリファレンス。

```sh
pip install -r requirements.txt
SCP_VF_U=... SCP_VF_I=... MONA_VF=... \
  python scripts/build_latin.py           # dist/latin/SumiMoji-*.otf（10 面）
  python scripts/build_latin_vf.py        # dist/latin/SumiMoji[wght].otf, -Italic[wght].otf
SHS_DIR=... \
  python scripts/build.py                 # 両ファミリー（JP / Term × 10 面）
  python scripts/build.py "Regular"       # Regular系のみ（動作確認用）
python scripts/verify_latin.py dist/latin/SumiMoji-Regular.otf        # Sumi Moji の回帰テスト
python scripts/verify_latin_vf.py "dist/latin/SumiMoji[wght].otf"     # 可変版（SCP と突き合わせ）
python scripts/verify.py dist/SumiMojiJP-Regular.otf   # JP の回帰テスト
python scripts/golden.py <前の dist> dist                  # 2つのビルド出力の比較
NF_SYMBOLS=... python scripts/nerdpatch.py                 # Nerd Fonts 版
```

`SCP_VF_U` / `SCP_VF_I` / `MONA_VF` は `build_latin.py` だけが使い、
それぞれ Source Code Pro VF / Monaspace VF の Releases から取得する。
`build.py` は Source Code Pro / Monaspace の VF に直接触らず、代わりに
`SHS_DIR`（Source Han Sans JP）と `LATIN_DIR`（既定 `dist/latin`、
`build_latin.py` の出力先）を見る。`verify.py` は `SCP_VF_U` / `SCP_VF_I`
があれば `=` のバーを Source Code Pro のインスタンスと突き合わせる。
`SUMI_VERSION`（例 `5.0.0`）を立てると name テーブルにその版番号を刻む
（リリースワークフローがタグから渡す。未設定なら上流のリビジョンをそのまま
残す）。

`requirements.txt` には AFDKO（`otfautohint` で描き直したグリフにヒントを
付ける）も含まれる。ローカルでの試しビルドで時間を節約したい場合は
`SUMI_SKIP_AUTOHINT=1` を立てるとスキップできる。Term の全角グリフ約1.7万個
は描き直さず charstring の中で 100 ユニット右へ動かす（`shift_charstring`）
ので、Source Han Sans 自身のヒントがそのまま残り、ヒント付けは各面で
描き直した 1,300〜1,800 グリフだけで済む。ヒント付与後は cffsubr（AFDKO の
`tx`、`requirements.txt` に同梱）で CFF をサブルーチン化している。

## 仕組み

- 欧文レイヤーは Sumi Moji（`scripts/build_latin.py`、VF から先に組んで
  `dist/latin` に出力）から来る。Source Han Sans JP（CID-keyed CFF）を
  土台に、Sumi Moji が持つ全コードポイント（Regular で 1,335）へその
  グリフを 1 セルで接ぎ木し cmap を差し替える。Source Han Sans が持って
  いた全角グリフは `fwid` の代替として残す。追加 CID は疎な空間の空きを
  昇順割当（サブセット OTF の CID は不連続なため）
- 太さの一致は Sumi Moji 側（`build_latin.py`）で完結している——各面は
  SCP の名前付きインスタンスそのもので、その `=` バー厚に Monaspace VF の
  wght を二分探索で合わせ、Italic は SCP Italic VF + slnt 追随。`build.py`
  は Sumi Moji を無変換で載せ、和文はバーの合う Source Han Sans の面を
  使う（`build.FACES`）
- 合字は LigatureSubst。`calt`/`liga` は結合ルックアップ1つ＋文脈ガード
  （各合字の入力列全体をカバーするトリガールールを最長一致順に並べる。
  一致範囲を1文字だけにしてネストした LigatureSubst に残りを委ねる形は
  一致範囲外の消費が OpenType 未定義動作で DirectWrite が非対応だった
  ため）、ss01〜08 はグループ別ルックアップ、cv99 が .alt 切替
- 行間は Source Code Pro の値（hhea = typo = 984 / −273 / 0、
  `USE_TYPO_METRICS`）。win は Source Han Sans の宣言値（1160 / 288）。
  等幅メタデータ（`post.isFixedPitch` / PANOSE bProportion=9 /
  xAvgCharWidth）は各面で独自に設定・実測し、Windows Terminal 等の
  フォント選択に出るようにする
- 欧文・合字・（Term では）拡幅した全角グリフなど T2CharStringPen で
  描いたグリフは、最終アウトラインで測ったアライメントゾーン付きの
  専用 CID FontDict を割り当てたうえで AFDKO の otfautohint によりヒント
  を付与（Source Han Sans 由来のグリフは元のヒントのまま）

## ライセンス

フォント本体は上流と同じ [SIL OFL 1.1](https://github.com/adobe-fonts/source-han-sans/blob/master/LICENSE.txt)。
OFL の Reserved Font Name 規定に基づき、ファミリー名は `Source` も `Monaspace` も含まない `Sumi Moji JP` / `Sumi Moji`（v3.2.0 までは `Shoyu Code Pro JP`）。
