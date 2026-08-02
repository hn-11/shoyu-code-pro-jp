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
（ペアリング参照と行間メトリクス）なので、SHCJ ユーザーの見た目の連続性が保たれる。
半角レイヤの収録範囲と、SCP にない半角グリフのドナーは
[Source Han Mono](https://github.com/adobe-fonts/source-han-mono) から取る。

## 設計方針

**上流にあるものは移植する。伸縮は最終手段。** ある字がセル幅で必要なら、
まずその幅で設計されたグリフを上流から探す。見つからないときだけ変形する。

| 必要なもの | 供給元 |
|-----------|--------|
| 半角欧文・記号 | Source Code Pro（原寸、または 10/9 拡大） |
| 半角カナ・`｡｢｣､･`・`￨￩￪￫￬￭￮`・`×÷±§…‖†‡‰−` ほか | **Source Han Mono**（セル幅で設計済み） |
| 罫線 `─│┼` ・ブロック `█▀▄░` （Term） | Source Code Pro（原寸600、セルを食み出してタイル） |
| 合字50種 | Monaspace |
| 全角・和文 | Source Han Sans |

伸縮が残るのは、**どの上流もセル幅で持っていない**もの（`①` `○` `★` など
の囲み文字・幾何学記号）だけ。そこでも等方縮小はせず、高さを保って
必要な分だけ横を詰める。

半角カタカナは長らく advance 500 のまま入っていた（SHCJ 由来）。等幅フォント
では半角グリフは必ず1セルなので桁がずれる。Source Han Mono はこれを修正済み
で、しかも字ごとに手が入っている（カナは水平に伸長、`｡` は原寸のまま
字送りだけ調整、`￩` は垂直位置も変更）ため、自前の一律変形では再現できない。

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

| ファミリー | 半角:全角 | `=`バー | 用途 |
|-----------|-----------|--------|------|
| Shoyu Code Pro JP | 667:1000 (2:3) | 69 | エディタ用（SHCJ の見た目） |
| Shoyu Code Pro JP Term | 600:1200 (1:2) | 69 | ターミナル用 |
| Shoyu Code Pro JP 35 | 600:1000 (3:5) | 62 | SCP 原寸・原太（本家忠実） |

**Term** は発想を逆にした 1:2: 欧文を縮めず、**全角の送りを 1200
（=600×2）に広げてグリフを中央配置**する。欧文は SCP 原寸（600）に
太さ補正（SHCJ の CJK ペアリング 69/1000em に一致）を掛けたもの。
ターミナルのセルグリッドに厳密一致する。

罫線・ブロック要素は **Source Code Pro の原寸600グリフに差し替え**。
全角版を縮小すると線の太さまで縮んで本文と色が合わなくなり、隣のセルとも
繋がらなくなる。SCP はこれらを1セル設計で持っており、しかもインクを
セルから39ユニット食み出させてあるので隣接セルが重なって継ぎ目が出ない
（PlemolJP は同じ目的で全角罫線フォントを自前で描き起こしている）。
さらに縦罫線とブロックは**行ボックス全体に合わせて伸ばす**ので、
行をまたいで縦線が途切れず、`█` の上下に地色の筋も出ない。

その他の曖昧幅（EAW=A）文字は1セル版に差し替えるが、**高さは保ったまま**
横だけ必要な分詰める。`①` は `あ` の 99% の高さになる（等方0.6倍だった
ときは 66%）。

35 の太さ補正版（35W、バー69）も試作したが、実用サイズ（14px）で
知覚できない差だったため引退。Term は全角と常時並ぶ前提なので
理論的に正しい補正済みの値を採っている。

かつて 1:2 の Console 変種を作ったが引退させた。SCP のゆったりした骨格を
500 セルに収めるには等方縮小（欧文が25%小さく細い）か約17%のコンデンス化
（線コントラストも歪む）しかなく、実際に両方ビルドして目視評価した結果、
どちらも SCP の字形を名乗るには失うものが多すぎた。1:2 が必要なら Iosevka
系（Sarasa）のような細身設計の欧文を使うフォントが素直（機構は
`rescale(ky=)` / `narrow_ambiguous()` として残してある）。

各ファミリー 7ウェイト（ExtraLight / Light / Normal / Regular / Medium /
Bold / Heavy）× 2スタイル（Upright / Italic — Italic は SCP の本物の
イタリック、和文は SHCJ と同じく直立のまま）。

### Nerd Fonts 版

全ての静的出力に Nerd Fonts パッチ済み変種も生成する。NF ファミリー名は
日本語プログラミングフォントの慣習（HackGen / PlemolJP / UDEV Gothic と同じ）
に合わせ**変種名の後ろ**に付く: `Shoyu Code Pro JP NF` /
`Shoyu Code Pro JP Term NF` / `Shoyu Code Pro JP 35 NF`。CID-keyed CFF の
ままでは font-patcher がグリフを Unicode で引けないため、パッチ前に
FontForge の `cidFlatten()` で平坦化している（アウトラインは無変換）。

### バリアブル版

各ファミリーに wght 軸（250–900）を持つ1ファイル版もある。
`ShoyuCodeProJP-VF.otf` / `ShoyuCodeProJP35-VF.otf` / `ShoyuCodeProJPTerm-VF.otf`。

土台は Source Han Sans の**バリアブル版**。静的7ウェイトは Adobe が
ウェイトごとに重なり除去をしているため互いに補間互換ではなく
（`あ` が 50/49/49/49/46/46/45 点）、束ねてもバリアブルにはできない。

欧文レイヤは名前付き7ウェイトぶんのマスターを持ち、CFF2 の `vsindex` で
和文（マスター2つ）とは別の VarData を参照する。ペアリングは静的版と同じ
実測ルールで、全ウェイトで `=` バーの誤差 0.4 ユニット以内。
軸の既定値は Regular（Source Han Sans は最軽量が既定なので、ウェイトを
指定せず読み込むと ExtraLight になってしまう）。

35 のバリアブル版では欧文が**Source Code Pro の座標そのまま**になる。
静的版は 10/9 拡大 → 600/667 縮小の往復で丸めが2回入るが、原寸600で
直接置けば往復自体が不要なため。

Italic も各ファミリーにある（`ShoyuCodeProJP35-VFItalic.otf` など）。軸では
なく別ファイルなのは、Source Code Pro の直立体とイタリック体が別デザイン
（`a` の一階建てなど）で、補間できるマスターが存在しないため。和文は静的版
と同じく直立のまま。

Nerd Fonts 版は静的のみ（font-patcher が FontForge ベースで VF 非対応）。


## 既知の制限

上流に由来し、こちらでは直せないもの。

**Term Heavy の欧文が7%軽い。** Term は欧文の太さを和文に合わせる変種だが、
Heavy で必要な 129 ユニットのバーには Source Code Pro の原寸600では届かない
（上限は 120、129 には wght 1012 相当＝軸の12.5%外が必要）。文字を軸外に
外挿すると Source Code Pro の字形が変わるため、120 で頭打ちにしている。
ビルド時に警告が出る。

**VF で半角カナ28字が全ウェイトを追従しない。** Source Han Mono は静的面
しか無く、Adobe がウェイトごとに重なり除去をしているため、同じ字でも面に
よって輪郭の構造が違う。形が一致するマスターだけで変化させているので、
最後のマスターより先では止まる（`ｱ` `ｲ` `ｵ` `ｸ` `ｺ` `ﾀ` は Medium まで、
`ｷ` `ﾔ` `ｬ` は Regular で固定）。静的版は影響を受けない。Source Han Mono に
バリアブル版が出れば解消する。

**ExtraLight / Light の合字は Monaspace を軸外に外挿している。** Monaspace の
最も細い `=` は 59 ユニットで、SHCJ ExtraLight が要求する 31 に届かない
（全5ファミリーが同じ下限）。演算子50種のみ・棒と点が主体の形状なので
外挿しており、全ドナーで退化・輪郭反転が無いことを自動検査している。

**`①` `○` `★` 等は縮小している。** これらを1セル幅で設計している上流が
無いため。Monaspace は 613 字中 257 字を持つが、欧文キャップハイト基準の
設計なので600セルに入れると `①` が 586 ユニット高（`あ` の 69%）になり、
全角を縮めた現状の 838（99%）より悪化する。採用しない。

**VF は重なりを保持している。** マスターが重なりを持たないと補間できない
ため（Adobe の Source Han Sans VF も同じ）。静的版は重なり除去済み。

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

上流（Source Han Sans JP 静的 + VF / Source Code Pro VF / Monaspace VF /
Source Han Code JP / Source Han Mono）を取得して環境変数で場所を渡す。
具体的なコマンドは `.github/workflows/ci.yml` の手順がそのまま実行可能な
リファレンス。

```sh
pip install -r requirements.txt
export SHS_DIR=... SHS_VF=... SCP_VF_U=... SCP_VF_I=... MONA_VF=...
export SHCJ_TTC=... SHMONO_TTC=...

python scripts/build.py                  # 静的 全ファミリー（3 × 14面）
python scripts/build.py "Regular"        # Regular系のみ（動作確認用）
python scripts/build_vf.py               # バリアブル 全ファミリー
python scripts/build_vf.py 35            # 35 のみ
python scripts/verify.py dist/ShoyuCodeProJP-Regular.otf   # 回帰テスト
python scripts/nerdpatch.py <FontPatcher dir>              # NF 変種（静的のみ）
python scripts/makeotc.py                                  # .ttc 化
```

## 仕組み

- Source Han Sans JP（CID-keyed CFF）を土台に、Source Han Mono が半角に
  している 590 コードポイントへ SCP VF 由来のグリフを接ぎ木し cmap を
  差し替える（SCP に無い半角カナ等は Source Han Mono から複写）。追加 CID は
  疎な空間の空きを昇順割当（サブセット OTF の CID は不連続なため）
- 各面の `=` バー厚を実測し、SCP / Monaspace VF の wght を二分探索して
  太さを一致させる。Italic は SCP Italic VF + slnt 追随
- 合字は LigatureSubst。`calt`/`liga` は結合ルックアップ1つ（最長一致の
  保証のため）、ss01〜08 はグループ別ルックアップ、cv99 が .alt 切替
- 行間・等幅メタデータは SHCJ の宣言値を複写し、レンダリング上の連続性を保つ
- バリアブル版は Source Han Sans VF を土台にし、JP へサブセットしてから
  （OTC の各面は 65535 グリフ = OpenType の上限ちょうどで、1字も足せない）
  同じレイヤを blend 付き CFF2 charstring として接ぎ木する

## ライセンス

フォント本体は上流と同じ [SIL OFL 1.1](https://github.com/adobe-fonts/source-han-code-jp/blob/master/LICENSE.txt)。
OFL の Reserved Font Name 規定に基づき、ファミリー名は変更済み（Source→Shoyu、nerd-fonts の SauceCodePro と同じ流儀の言い換え）。
