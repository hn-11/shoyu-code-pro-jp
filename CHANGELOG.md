# Changelog

## Unreleased

- セルフレビューで見つけた不具合の修正:
  - JP 各面の合字グリフ（61 種 + cv99 の 2 種）の CFF charstring 幅が
    hmtx の送り幅と 510u ずれていた（記号用 FD の nominalWidthX で符号化
    した後に `add_latin_fd` が A の FD 複製へ移していたため。描画は hmtx を
    読むので見た目には出ないが、CFF を読む処理には誤った幅が見えていた）。
    `latin_ligatures` も他の追加処理と同じ A の FD で追加するようにし、
    `verify.py` が全グリフの CFF 幅と hmtx の一致を検査する
  - 600 セルの 35 / Term ファミリーで半角記号 ￨￩￪￫￬￭￮（U+FFE8〜FFEE）の
    送り幅が 500 のままだった（`HALFWIDTH_FORMS` が U+FFDC で止まって
    いた）。East Asian Width "H" の 2 範囲を対象にし、`verify.py` が
    U+FFE9 を検査する
  - `makeotc.py` / `nerdpatch.py` の `SumiMoji-*.otf` 探索が VF の
    `SumiMoji-Italic[wght].otf` も拾い、リリースの TTC 化が 13 面で止まり
    Nerd Fonts パッチが CFF2 の VF を受け取る状態だった。静的面だけを
    列挙する `verifylib.static_faces` に置き換え
  - Sumi Moji VF: `head` の外接矩形と `hhea` の広がり（xMaxExtent・両側の
    最小サイドベアリング）が既定マスター（Regular）だけの値だったのを、
    各マスターのアウトラインから測った和にした（保存時の再計算は既定
    インスタンスしか見ないので切る）。`verify_latin_vf.py` は軸の両端と
    既定のインスタンスを丸めなしで描き、外接矩形と hhea の 3 値を
    突き合わせる。GSUB の FeatureParams を付け替えた
    後に元の name レコード（Upright で 73 件）が参照されないまま残って
    いたのと、SCP 由来の STAT / fvar の文字列 5 件を削除（`prune_orphan_names`、
    静的面にも適用）。
    `harmonize_win_metrics` は実行した面だけでなく出力ディレクトリ内の
    ファミリー全面を対象にする（CI は Regular と Light Italic を別ステップ
    で組む）。SCP VF のマスター位置の読み取りを wght 軸に限定
  - `requirements.txt` の fontTools 下限を 4.52.4 に（`cffLib.CFF2ToCFF` と
    `instantiateCFF2(round=)` を使うため。4.50 では import で落ちる）
  - 結合文字の異体（cv11: U+0306 のキリル文字用ブレーヴェ）が送り幅 1 セルの
    グリフとして取り込まれていたため、cv11 を有効にするとアクセントが
    1 セル分の幅を取っていた。既定の結合文字と同じ 0 幅・1 セル左寄せで
    取り込み、GDEF でもマークに分類する。`verify.py` が cv11 の前後で
    U+0306 の送り幅 0 を検査する
  - `_shcj_ref` がプール内で `sys.exit` していたのを例外に（他の面の
    失敗と一緒に報告される）。`verify_latin_vf.py` は wght 軸が無い
    フォントで FAIL を出して終了する
- ビルド時間の短縮: Term の全角グリフ約1.7万個は描き直さず charstring の
  中で右へ動かす（`shift_charstring`——先頭の vstem 座標と最初の moveto
  だけを動かし、幅オペランドを付け替える）ので、Source Han Sans 自身の
  ヒントが残り、Term 1 面のヒント付けが 99 秒から 10 秒前後になった
  （品質面でも、自動ヒントより元のヒントが残るほうがよい）。
  `nerdpatch.py` は面ごとの FontForge 実行をコア数分並列に、
  `build_latin_vf.py` は Upright と Italic を並列に組む。CI は可変フォント
  を別ジョブで並行して組む。JP の Regular 6 面はローカル 4 コアで
  2 分（以前は 9 分）。
  さらに、保存のたびに fontTools が外接矩形と hhea / vhea の広がりを
  求め直すために全グリフ（JP 1 面あたり約 1.9 万）を 3 回描き、描いた
  charstring を全部コンパイルし直していたのをやめ、`update_bbox` が
  1 回の走査で head / CFF FontBBox / hhea / vhea を揃えて（値は fontTools
  の再計算と同一）、以後の保存（面の保存、otfautohint、cffsubr、
  `makeotc.py`、`nerdpatch.py`）は再計算なし。走査で解いた charstring の
  バイトコードは戻すので、触っていないグリフは読んだままの形で書き出す。
  otfautohint は子プロセスではなく同一プロセスで呼ぶ（その保存も再計算
  なし）。`=` バーの二分探索は VF をインスタンス化せず
  `getGlyphSet(location=)` で各位置のアウトラインを直接読む（1 プローブ
  0.8〜2.3 秒 → ほぼ 0 秒。丸めなしのバーを見るので、収束位置が以前と
  1 wght 前後ずれ、静的 Sumi Moji のアウトラインが 1〜2u 動く）。
  ローカル 4 コアで、JP Regular 6 面 55 秒（2 分 → ）、Sumi Moji Regular
  6 面 15 秒（64 秒 → ）、VF Upright 21 秒（3 分 → ）、`verify_latin_vf.py`
  61 秒（112 秒 → ）、TTC 6 面 3 秒（42 秒 → ）。
  ワークフローはマトリクスに分割: CI は Regular / Regular Italic /
  Light Italic / Nerd Font（Term Regular と Sumi Moji Regular のパッチ）/
  可変フォントを並列の 5 ジョブで組み、`build` ジョブが集約する
  （`upstream-sync.yml` が待つジョブ名は変わらない）。リリースは
  ウェイト × 書体の 12 ジョブがそれぞれ Latin ドナー・JP 3 面・NF
  パッチまで組んで検証し、可変フォント 2 ジョブと並行、`package`
  ジョブがアーティファクトを集めて Sumi Moji（静的・NF）の
  usWinAscent/Descent をファミリー全体で揃え（`harmonize_latin.py`）、
  VF を静的面と突き合わせ、TTC・zip・リリースを作る。面フィルタは
  語の組み合わせになり、「Light Upright」「Regular Upright Term」の
  ように書体（Upright / Italic）と変種を絞れる。共通の準備手順は
  `.github/actions/setup-build`
- リファクタリング: 7 箇所に複製されていたグリフ追加の前置き
  （`append_context`）、方針の違う 4 箇所の cmap 書き込み（`set_cmap`）、
  `build.py` / `build_latin.py` の `main()` と面の後処理
  （`env_paths` / `run_faces` / `write_face`）、STAT 構築（`add_stat` が
  静的面の 1 値と VF の全値の両方を担当）、SHCJ のバー目標
  （`shcj_bar_target`）、VF 側の wght 探索（`VFSource.matched_wght` /
  `floor_bar` — 静的面と同じ探索になり、VF の名前付きインスタンスが
  静的面と厳密に同じ位置に乗る。実測の位置は Upright 317/374/406/545/
  670/857、Italic 317/377/399/538/661/841 と 1 前後動いた）を共通化。
  name テーブルの nameID 5（Version）も `OWNED_NAME_IDS` に含め、書き換え
  前に旧レコードを全プラットフォーム分消す。`build_latin.py` もフィルタ
  無しの実行では古い面を先に消す。検証・梱包スクリプト共通の
  `scripts/verifylib.py`（HarfBuzz シェイパー、ok/FAIL 集計、ヒント
  検出、静的面の列挙）。未使用の `mona_onecell` と 667 セル前提の
  `MONA_K` 既定値、`fetch-upstreams` の未使用 `cache` 入力を削除。
  面数が 3 以上ならフィルタ付きでもプロセスプールで組む
- ドキュメント: CONTRIBUTING が旧い 1 段階ビルドを説明していたのを 2 段階
  に更新。README / CHANGELOG の「Sumi Moji に TTC・NF は無い」を訂正
  （リリースは `SumiMoji.ttc` / `SumiMoji-NerdFont.zip` を添付済み）

## v3.3.0

- `scripts/build_latin_vf.py` を追加: Sumi Moji を CFF2 可変フォントとして
  組む（`dist/latin/SumiMoji[wght].otf` / `SumiMoji-Italic[wght].otf`）。
  マスターは SCP VF 自身のマスター位置（wght 200 / 400 / 900、CFF2 の
  VarStore から実測——決め打ちしない）にそのまま置き、各マスターで
  Monaspace を太さ一致でインスタンス化するが、erosion（Monaspace の
  wght 下限対策）は非線形なブーリアン演算でマスター間の補間に使えない
  ため無効化し（`VFSource.matched(erode=False)`、下限で単にクランプ）、
  重なり除去（`pathops.simplify`、`draw_clean(simplify=False)`）も
  マスター間の点対応を崩すため行わない——重なりは SCP 自身の VF と同じ
  扱いで残す。ヒント付け・サブルーチン化もしない。fvar の6つの名前付き
  インスタンス（Light/Normal/Regular/Medium/Bold/Heavy）と STAT の値は
  静的版の STAT と同じ usWeightClass の値（300/350/400/500/700/900、
  既定 400 = Regular で OS/2 usWeightClass と一致——軸を指定せずに VF を
  選んでも Regular が出る）。avar が各値を静的版と同じ「SHCJ の `=`
  バー×600/667」に一致する SCP wght（実測: Upright で 317/374/406/546/
  669/857、Italic で 317/378/399/538/662/841）へ写す。マスターを置く
  設計座標は SCP のユーザー wght を SCP 自身の fvar 正規化 + avar で
  線形化したもの（SCP の VF はユーザー wght に対して線形ではない）で、
  SCP 自身の avar の折れ点も写像に含めるため、名前付きインスタンスの
  間でも SCP と一致する。マスターは fontTools の instancer の整数丸めを
  切ってインスタンス化する（`unrounded_cff2_instancing`）——charstring の
  オペランドは相対座標なので丸めが経路に沿って累積し、丸めたマスターから
  組むと `m` などがマスター間で最大 10u ずれていた（実測）。丸めなしなら
  SCP のブレンドそのもの（CFF2 charstring の固定小数 16.16 精度）を補間
  するので、`verify_latin_vf.py` は名前付きインスタンスの間の wght でも
  SCP 自身のブレンドと 1u 以内で一致することを確認する。代償として
  VF のファイルサイズは整数版の約 4.5 倍（Upright 約 1.6MB——
  オペランドが 16.16 固定小数 5 バイトになるため）。マスターは SCP の 200 / 400 に
  Regular と Heavy の位置（Regular が既定マスター、Heavy が軸の上限）と
  Monaspace の下限位置（Monaspace wght 200 のバーが SCP のバーと一致する
  SCP wght——これより細い側は Monaspace が下限でクランプされ一定、太い側
  は SCP 追随）を加えた 5 つ。name テーブルは SCP VF 自身の慣習
  （`SourceCodeVF-Upright.otf` / `-Italic.otf`）に倣い、nameID 6 に
  `SumiMoji-Roman` / `SumiMoji-Italic`、nameID 25 に `SumiMoji`
  （バリエーション PostScript 名接頭辞）、nameID 16/17 は省略（fvar +
  STAT が既に家族を説明するため）。軸の既定値に置かれた名前付き
  インスタンス（Regular / Italic）の postScriptNameID は fvar の仕様
  どおり nameID 6 を指す（fontbakery
  `opentype/varfont/valid_default_instance_nameids`）。MVAR/HVAR は除外（このレシピでは
  送り幅もOS/2の縦メトリクスも太さで変化しないため、可変にする対象が
  無い）。SCP wght がおよそ366を下回ると Monaspace 側の記号・合字は
  自身の wght 200 の下限（静的版が erosion で削っている太さ）より
  薄くできないため、VF の軽量側では記号だけが下限の太さで止まり、
  erosion 済みの静的 Light よりわずかに太くなる——静的 Light は引き続き
  erosion 版を配布する。`scripts/verify_latin_vf.py` を追加（fvar/STAT/
  name の形状、6つの名前付きインスタンス全てでの合字シェイピング、
  6 つの名前付きインスタンスそれぞれの `=` バーと `A` の外接矩形を対応する
  静的面と比較、`SCP_VF_U` / `SCP_VF_I` がある環境では名前付き
  インスタンスの間の wght でも SCP 自身のインスタンスと外形が一致する
  ことを確認）。CI（`ci.yml`）は `build_latin.py` の Regular 検証の
  直後に Upright VF のビルドと検証を追加（時間短縮のため Upright のみ）、
  リリース（`release.yml`）は Upright・Italic 両方をビルド・検証し、
  `SumiMoji.zip` にも自動的に含まれる（zip 手順は `dist/latin` 内の
  `*.otf` を素朴に glob しているため）

- name テーブルから nameID 7（商標: "Source is a trademark of Adobe"）と、
  静的面では nameID 25（バリエーション PostScript 名接頭辞、SCP 由来の
  `SourceCodeUpright` / `SourceCodeItalic` が残っていた）を落とす
  （`build.OWNED_NAME_IDS`）——どちらも Source という名前のフォントの
  ためのもので、Adobe の表示は nameID 0 のクレジットに入っている。
  Sumi Moji（静的・VF とも）では SCP が GDEF のマーク分類を付けていない
  結合文字 U+035F / U+0361 も class 3（Mark）にする
  （`build.classify_unicode_marks`）
- 欧文のみの新ファミリー Sumi Moji（仮称、PostScript 名 `SumiMoji-*`）を
  追加し、`build.py` はこれを Source Han Sans に接ぎ木する側に変更
  （VF に直接触らなくなった）。`scripts/build_latin.py` が VF から直接
  組む: Source Han Code JP の `=` バーに合わせた Source Code Pro VF の
  インスタンスを fontTools の CFF2ToCFF で静的 CID-keyed CFF に変換した
  ものをベースに（SCP のアウトライン・アライメントゾーン・GSUB
  （`cv01`〜`cv17` `zero` `salt`、SCP の stylistic set は `ss11`〜`ss17`
  に移動）・GPOS のマーク位置決めはそのまま生存）、インスタンス化で
  失われるヒントを SCP 自身のゾーンに対して otfautohint で付け直し、
  Monaspace の合字61種・ASCII 記号32字・1セル矢印（SCP に無い `⇔` も
  追加）を接ぎ木し、cffsubr でサブルーチン化する。プロファイルは2つ:
  配布物 `dist/latin`（バー = SHCJ のバー × 600/667、35 と同じ太さ）と
  内部専用 `dist/latin/term`（バー = SHCJ のバー を 600 のまま、Term
  ファミリー用ドナー）。結合文字は SCP が出荷する形（スペーシング、
  GPOS mark で位置決め）のまま。縦メトリクスは SCP 自身の hhea
  （984/-273）、typo を hhea と同値にして `USE_TYPO_METRICS` を立て、
  win はファミリー全面のバウンディングボックス（Regular ペアで
  1060/454）。Regular は1,632グリフ/約140KB、Italic は1,335グリフ
  （SCP Italic VF のグリフ数がそもそも少ない）。CI（`ci.yml`）は
  `build_latin.py` を先に走らせてから Regular ペアをビルド・検証、
  リリース（`release.yml`）も同じ順序で12面をビルドし2面を検証した
  うえで `SumiMoji.zip`（LICENSE 同梱）をリリース資産に追加。JP 側の
  出力は roundoff（±1〜2ユニット）を除き従来の VF 直接ビルドと同一に
  なるよう意図しており、`scripts/golden.py` が2つの dist ディレクトリ
  間で cmap・送り幅・シェーピング・アウトライン（許容誤差つき）・
  メタデータ・ヒントを比較する。`makeotc.py` / `nerdpatch.py` も
  Sumi Moji を扱い、リリースは `SumiMoji.ttc` と `SumiMoji-NerdFont.zip`
  も添付する
- 合字を50種から61種に拡張。Monaspace が描いているが `data/mona_ligs.json`
  が未収録だった11種を追加: 真の合字5つ `!~` `=~`（正規表現マッチ、ss01）、
  `~~>`（ss02）、`<!--`（ss03、4セル）、`&&=`（ss08）と、`::`/`:=` と同じ
  手法で合成する文脈的スペーシング代替6つ `&&` `++`（`&`/`+` の
  init/fina 変異、ss08）、`..<` `.=`（ピリオドを上げた変異、ss06）、
  `:>` `<:`（コロンを上げた変異、ss05）。結果として `&&=` と `~~>` は
  合字化するようになった（Monaspace 本家と同じ挙動）。文脈ガードは
  `<|>` `->>` `==>` を引き続き素の文字のまま保つ
- JP / 35 の全角矢印7種（`←` `→` `↑` `↓` `⇐` `⇒` `⇔`）を Monaspace から
  取り直し。合字グリフ（`->` `<-` `=>` `<=>`、`⇐` は `=>` の鏡像、
  `↑` `↓` は `->` の 90° 回転）の軸を詰めるか伸ばすかして Source Han
  Sans のインク長に合わせる（Italic は傾斜を抜いてから加工して後で
  掛け直す）。全角の幅・インク量は SHCJ のまま、矢尻とストロークが
  合字と同一になる。Monaspace 自身の `→` 文字は `->` より矢尻が小さい
  ので使わない。`≠` `≤` `≥` `…` は軸がないため引き続き Source Han Sans
  の全角グリフ
- 合字と対になる11字（矢印7種 + `≠` `≤` `≥` `…`）に、全ファミリーで
  全角・半角（Monaspace 1セル）両方の字形を用意し OpenType feature で
  手動切り替え可能に: JP / 35 は既定が全角で `hwid` / 新設の `ss09`
  （「Half-width arrows & operators」、この11字だけを動かす）が半角、
  Term は既定が半角（従来どおり）で `fwid` が全角に戻す。フォントは
  ターミナルの曖昧幅設定を検知できないための手動対応。HackGen Console /
  PlemolJP Console / Moralerspace HW / UDEV Gothic JPDOC は別ファミリーで
  この使い分けを提供しているが、本フォントは各ファミリー内の feature
  として持たせている
- 単独の ASCII 記号は32字全部（`!"#$%&'()*+,-./:;<=>?@[\]^_`{|}~`）を
  Monaspace に統一（以前は `=` `<` `>` `|` `~` の5字のみ）。合字自体が
  Monaspace 製のため、記号の骨格が単独字と合字とで食い違うと隣接時に
  継ぎ目が見えていた（`#` と `#[`、`-` と `->` など）。多くは Monaspace の
  cap 高・x-height が高いぶんの縦サイズ差（16〜150u、セル内に収まり
  ターミナルサイズでは2ピクセル未満）。`-` は `=` より124u短いが
  Monaspace 自身の字形どおり。SCP の cv14/cv15/cv16 を有効にすると
  `-` `*` `$` は SCP の字形に戻る
- 合字の calt/liga: 結合ルックアップの一致条件を、先頭1文字だけを見て
  残りをネストした LigatureSubst に委ねる形から、各合字の入力列を全部
  カバーするトリガールール（最長一致順）に変更。ネストしたルックアップが
  一致範囲を超えて何文字消費してよいかは OpenType の未定義動作で、
  HarfBuzz（kitty / WezTerm / Ghostty / VS Code のエディタ本体）は許容
  していたが DirectWrite（Windows Terminal）は v3.2.0 で `->` を素の文字
  のまま描画していた。Monaspace 本家の calt も入力を全部カバーする形。
  なお VS Code の統合ターミナル（xterm.js のリガチャアドオン、
  font-ligatures）は Fira Code 式の単純な置換ルールしか解釈せず、
  このフォントの合字はどのバージョンでも表示されない — これは今回の
  変更と無関係で従来通り
- 等幅メタデータ: `post.isFixedPitch=1`、PANOSE bProportion=9
  （HackGen / PlemolJP と同じ）、xAvgCharWidth を OS/2 v3+ の定義
  （0でない送り幅全部の平均）で再計算 — SHCJ の値の複写をやめた。
  Windows Terminal のフォント選択に「すべてのフォントを表示」なしで
  出るようになる
- OS/2 sxHeight / sCapHeight を各面の実際の `x` / `H` から実測。
  SHS の値（543/733）は Term/35（SCP 原寸で 488/655）に対して誤りだった
- ヒンティング: T2CharStringPen で描いた欧文・合字・（Term では）拡幅した
  全角グリフはこのフォント最初のバージョンから CFF ヒントを持っていな
  かった（SHCJ の欧文にはヒントがあった）。最終アウトラインで測った
  アライメントゾーン（BlueValues/OtherBlues/StdHW/StdVW）付きの CID
  FontDict を新設して割り当て、面を保存した後に AFDKO の otfautohint で
  ヒントを付ける（`requirements.txt` に afdko 追加、
  `SHOYU_SKIP_AUTOHINT=1` でローカルビルド時はスキップ可）。Source Han
  Sans 由来のグリフは元のヒントのまま。ヒント付与後、cffsubr（AFDKO の
  tx、`requirements.txt` に追加）で CFF をサブルーチン化: ビルドが生成
  する charstring はすべてフラットで、Term は全角グリフ約1.7万個を
  丸ごと再生成するため、ヒント付きだと Term の面が44%肥大（6.7MB）して
  いた。サブルーチン化後は4.6MB — ヒントを保ったまま v3.2.0（4.66MB）より
  小さい
- GDEF: SCP から移植した結合文字（U+0300〜036F、送り0）を class 3
  （Mark）に分類
- 来歴: nameID 0 にプロジェクトの著作権表示に加え Source Han Sans /
  Source Code Pro / Monaspace 各ドナーの表示をビルド時に取り込んで記載、
  nameID 9 にドナーのデザイナーを列挙、nameID 8 / 11 が Adobe ではなく
  プロジェクト（hn-11、リポジトリ URL）を指すように変更、
  OS/2 achVendID を Adobe の `ADBO` から未登録の `SHYU` に、
  nameID 3（unique ID）を `version;SHYU;PostScriptName` 形式に。
  Source Han Sans の古い DSIG は削除
- STAT テーブルを追加。各面は自分自身の wght / ital 値を1つずつだけ
  持つ（Regular は elidable で Bold にリンク、upright は elidable で
  Italic にリンク） — ファミリー全体の値を全面に列挙する形は Windows の
  ファミリーモデルを混乱させる（fontbakery: STAT_in_statics）ため
  避けた。OS/2 に WWS ビットを立て（version 4 に更新）、usWeightClass も
  ウェイトごとに明示的に設定

## v3.2.0

- 合字に文脈ガードを追加（Monaspace 本家の calt と同じ考え方）。演算子の並びが
  どの合字よりも長いときは合字化しない: `<|>` `&&=` `~~>` `->>` `==>` は
  素の文字のまま、`->` `-->` `<-->` `>>=` `===` は従来どおり合字。

## v3.1.0

- Light ウェイト復活（Monaspace 下限を超える分をアウトライン削りで合わせる）
- リリース版数を name ID 5 / fontRevision に刻印
- SCP の未収録約 600 字（`ł` `ğ` `ş` `ı` `ř` `₽` …）を半角で取り込み
- `−` `ς` `⁴` などのグリッド外グリフ修正
- 35/Term で半角カナを 1 セルに中央配置
- Term/35: `pwid`/`palt` を外し `hwid` 先のグリフをセルに合わせる
- NF 変種のアイコンを JP/35 でも 1 セル幅に
- 結合文字（U+0300〜036F）を送り 0 で取り込み、直前の文字に重なるように
- OS/2 の Unicode / コードページ範囲ビットを最終的な収録文字から再計算
- `makeotc.py` がファミリー内で cmap が一致しない面を検出して止まるように
- リリース zip に LICENSE 同梱

## v3.0.0

破壊的変更を含みます。

- ExtraLight/Light 削除（Light は 3.1.0 で復活）
- `= < > | ~` を Monaspace に
- Term の曖昧幅を HackGen Console 方式に変更

**既存ユーザーへの影響**: Term で `①` `※` が 2 セル幅になり、曖昧幅を
半角扱いするターミナルでは右隣に食み出す。Windows Terminal は
`"compatibility.ambiguousWidth": "wide"` で 2 セル確保できる。`←` `→` `≠`
`≤` `…` は 1 セル（Monaspace 版）。

- liga 単独で合字が出なかったバグ修正
- Term が CI で検証されるように
