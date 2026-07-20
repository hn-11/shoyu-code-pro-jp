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

**Monaspace 由来の50種**を収録（[githubnext/monaspace](https://github.com/githubnext/monaspace) v1.400、OFL）。
主要どころ: `!=` `==` `===` `!==` `<=` `>=` `->` `<-` `=>` `~>` `:=` `::`
`<<=` `>>=` `=<<` `|>` `<|` `<>` `</>` `//` `#[` `...` `&&` `||` ほか（全50種）。
全リストは `data/mona_ligs.json` を参照。

移植するのは演算子グリフのみで、英数字は SHCJ（= Source Code Pro）のまま。
線の太さは**面ごとに** SHCJ の `=` のバー厚を実測し、Monaspace VF の wght を
二分探索で一致させたインスタンスから取り込む。Italic 面には slnt 軸で傾斜も
追随させ、ベースラインは両フォントの `=` の縦中心を揃える。
GSUB は `calt` / `liga` 両登録（全合字が既定で有効）。加えて Monaspace 流の
**グループ別 stylistic set** を備え、`calt` を切って必要な群だけ有効化できる:

| feature | 内容 | 例 |
|---------|------|----|
| ss01 | 比較・等価 | `!=` `===` `<=` `>=` |
| ss02 | 矢印 | `->` `<-` `=>` `>>=` |
| ss03 | マークアップ | `</` `/>` `</>` `<>` |
| ss04 | パイプ | `\|>` `<\|` |
| ss05 | コロン | `::` `:=` |
| ss06 | ドット | `..` `...` |
| ss07 | コメント | `//` `#!` |
| ss08 | 反復・論理 | `&&` `\|\|` `<<` `>>` |
| cv99 | 演算子の代替デザイン（Monaspace の .alt） | |

さらに **Source Code Pro 自身の字形バリアントを貫通**させている:
`zero`（スラッシュゼロ切替）、`cv01`〜`cv17`（`a` の一階建て、`g` の形など
SCP 純正の文字変異）、`salt`、SCP の stylistic set は ss11〜ss17 に +10 で
マウント（ss01〜ss08 は合字グループが使用）。等幅メタデータ
（`post.isFixedPitch` / PANOSE / xAvgCharWidth）と行間は SHCJ の宣言値を複写。

```jsonc
// 例: !== の一体化が読みにくい場合、比較系だけ切って矢印は残す
"editor.fontLigatures": "'calt' off, 'ss02', 'ss03', 'ss05', 'ss06', 'ss07', 'ss08'"
```
`:=` と `::` は Monaspace 内でも文脈変異（`colon.case`）で実現されているため、
同グリフの合成として取り込んでいる（実レンダリングと誤差1ユニット未満で一致）。

## ファミリー構成

| ファミリー | 半角:全角 | 用途 |
|-----------|-----------|------|
| Shoyu Code Pro JP | 667:1000 (2:3) | エディタ用 |
| Shoyu Code Pro JP Term | 667:1334 (1:2) | ターミナル用 — 欧文は 2:3 と同一 |
| Shoyu Code Pro JP 35 | 600:1000 (3:5) | Source Code Pro 原寸（本家プロポーション） |

**Term** は発想を逆にした 1:2: 欧文を縮めるのではなく**全角の送りを
1334（=667×2）に広げてグリフを中央配置**する。欧文レイヤーは 2:3 と
バイト単位で同一のまま、ターミナルのセルグリッドに厳密一致し、罫線も
繋がる。曖昧幅（EAW=A）の `×` `±` `…` や罫線素片は 667 の1セル版に
差し替え、全角側は字間が空くが対称（SHCJ をターミナルで使ってきた
見た目の整流版）。

かつて 1:2 の Console 変種を作ったが引退させた。SCP のゆったりした骨格を
500 セルに収めるには等方縮小（欧文が25%小さく細い）か約17%のコンデンス化
（線コントラストも歪む）しかなく、実際に両方ビルドして目視評価した結果、
どちらも SCP の字形を名乗るには失うものが多すぎた。1:2 が必要なら Iosevka
系（Sarasa）のような細身設計の欧文を使うフォントが素直（機構は
`rescale(ky=)` / `narrow_ambiguous()` として残してある）。

各ファミリー 7ウェイト（ExtraLight / Light / Normal / Regular / Medium /
Bold / Heavy）× 2スタイル（Upright / Italic — Italic は SCP の本物の
イタリック、和文は SHCJ と同じく直立のまま）。

35 は半角グリフを 600/667 に等方縮小したもの（= オリジナル SCP の原寸復元）。全出力に Nerd Fonts
パッチ済み変種も生成する。NF ファミリー名は日本語プログラミングフォントの
慣習（HackGen / PlemolJP / UDEV Gothic と同じ）に合わせ**変種名の後ろ**に付く:
`Shoyu Code Pro JP NF` / `Shoyu Code Pro JP Term NF` / `Shoyu Code Pro JP 35 NF`。CID-keyed CFF のままでは
font-patcher がグリフを Unicode で引けないため、パッチ前に FontForge の
`cidFlatten()` で平坦化している（アウトラインは無変換）。

## インストール

[Releases](../../releases) から OTF をダウンロードしてインストールし、

```jsonc
{
  "editor.fontFamily": "Shoyu Code Pro JP",
  "editor.fontLigatures": true
}
```

ファミリー名を `Shoyu Code Pro JP` にリネームしてあるので、
オリジナルと共存できる。

## ビルド

4つの上流（Source Han Sans JP / Source Code Pro VF / Monaspace VF /
Source Han Code JP）を取得して環境変数で場所を渡す。具体的なコマンドは
`.github/workflows/ci.yml` の手順がそのまま実行可能なリファレンス。

```sh
pip install -r requirements.txt
SHS_DIR=... SCP_VF_U=... SCP_VF_I=... MONA_VF=... \
  python scripts/build.py            # 全ファミリー（2:3 / 35 × 14面）
  python scripts/build.py "Regular"  # Regular系のみ（動作確認用）
python scripts/verify.py dist/ShoyuCodeProJP-Regular.otf   # 回帰テスト
python scripts/nerdpatch.py <FontPatcher dir>              # NF 変種
python scripts/makeotc.py                                  # .ttc 化
```

## 仕組み

- Source Han Sans JP（CID-keyed CFF）を土台に、SHCJ が半角にしている
  477 コードポイントへ SCP VF 由来のグリフを接ぎ木し cmap を差し替える
  （SCP に無い半角カナ等は SHCJ から複写）。追加 CID は疎な空間の空きを
  昇順割当（サブセット OTF の CID は不連続なため）
- 各面の `=` バー厚を実測し、SCP / Monaspace VF の wght を二分探索して
  太さを一致させる。Italic は SCP Italic VF + slnt 追随
- 合字は LigatureSubst。`calt`/`liga` は結合ルックアップ1つ（最長一致の
  保証のため）、ss01〜08 はグループ別ルックアップ、cv99 が .alt 切替
- 行間・等幅メタデータは SHCJ の宣言値を複写し、レンダリング上の連続性を保つ

## ライセンス

フォント本体は上流と同じ [SIL OFL 1.1](https://github.com/adobe-fonts/source-han-code-jp/blob/master/LICENSE.txt)。
OFL の Reserved Font Name 規定に基づき、ファミリー名は変更済み（Source→Shoyu、nerd-fonts の SauceCodePro と同じ流儀の言い換え）。
