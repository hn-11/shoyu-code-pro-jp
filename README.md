# Sauce Han Code JP

[Source Han Code JP](https://github.com/adobe-fonts/source-han-code-jp) に
プログラミング合字（リガチャ）を注入したフォント。

**通常の字形・メトリクスには一切手を加えない。** 合字グリフはフォント自身の
既存グリフ（`≠ ≤ ≥ ← → ≡ ≢` および `:` `=`）を 2〜3 セル幅に配置し直した
合成であり、輪郭の描き起こしは行っていないため、ストロークの太さ・スタイルは
本体と完全に一致する。半角:全角 = 2:3 のメトリクスもそのまま。

## 合字一覧

| 入力 | 表示 | セル幅 |
|------|------|--------|
| `!=` | ≠ | 2 |
| `<=` | ≤ | 2 |
| `>=` | ≥ | 2 |
| `->` | → | 2 |
| `<-` | ← | 2 |
| `===` | ≡ | 3 |
| `!==` | ≢ | 3 |

`==` は合字化しない（`===` との区別のため）。`:=` も合字化しない —
合成グリフ（colon 持ち上げ版・ベースライン版とも）を実際に試した結果、
目に馴染まず除外した。フォント内に ≔ の元グリフが存在しないため。GSUB の `calt` と `liga` の
両方に登録しているため、VS Code は `"editor.fontLigatures": true` だけで有効になる。

## ファミリー構成

| ファミリー | 半角:全角 | 用途 |
|-----------|-----------|------|
| Sauce Han Code JP | 667:1000 (2:3) | エディタ（VS Code 等） |
| Sauce Han Code JP Term | 500:1000 (1:2) | ターミナル（セルグリッド互換） |
| Sauce Han Code JP 35 | 600:1000 (3:5) | Source Code Pro 原寸（本家プロポーション） |

Term は半角グリフを 500/667 に等方縮小したもので、Adobe が Source Code Pro
(600) から SHCJ (667) を作った手順のちょうど逆方向。全出力に Nerd Fonts
パッチ済み変種（`*NerdFont*`）も生成する。CID-keyed CFF のままでは
font-patcher がグリフを Unicode で引けないため、パッチ前に FontForge の
`cidFlatten()` で平坦化している（アウトラインは無変換）。

## インストール

[Releases](../../releases) から OTF をダウンロードしてインストールし、

```jsonc
{
  "editor.fontFamily": "Sauce Han Code JP",
  "editor.fontLigatures": true
}
```

ファミリー名を `Sauce Han Code JP` にリネームしてあるので、
オリジナルと共存できる。

## ビルド

```sh
pip install -r requirements.txt
curl -sSfL -o upstream/SourceHanCodeJP.ttc \
  https://github.com/adobe-fonts/source-han-code-jp/releases/download/2.012R/SourceHanCodeJP.ttc
python scripts/build.py            # 全14面
python scripts/build.py "JP R"     # Regular系のみ（動作確認用）
```

`dist/` に個別 OTF が生成される。

## 仕組み

- 上流 TTC（CID-keyed CFF, 14面）を fontTools で面ごとに開き、合字グリフを
  CFF に追加（CharStrings / charset / FDSelect / hmtx / vmtx / maxp を更新）
- GSUB に LigatureSubst ルックアップを1つ追加し、`calt` / `liga` として
  全 script / langsys に登録。最長一致なので `!==` が `!=` に食われることはない
- 上流の Italic 面は CFF テーブルを立体と共有している（イタリック化は
  GSUB `ital` 側）ため、出力ファイル名は name テーブルの PostScript 名
  （name ID 6）を使う

## ライセンス

フォント本体は上流と同じ [SIL OFL 1.1](https://github.com/adobe-fonts/source-han-code-jp/blob/master/LICENSE.txt)。
OFL の Reserved Font Name 規定に基づき、ファミリー名は変更済み。
