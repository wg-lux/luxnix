{
  fetchurl,
  runCommand,
  unzip,
}:
let
  source = fetchurl {
    url = "https://github.com/explosion/spacy-models/releases/download/de_core_news_lg-3.8.0/de_core_news_lg-3.8.0-py3-none-any.whl";
    sha256 = "36fda650e476b54d5e87803635e36dadd1e8e034c4b5962088586d684f4c9fed";
  };
in
runCommand "de-core-news-lg-3.8.0-data" { nativeBuildInputs = [ unzip ]; } ''
  unzip -q ${source} 'de_core_news_lg/de_core_news_lg-3.8.0/*'
  mv de_core_news_lg/de_core_news_lg-3.8.0 "$out"
  test -s "$out/config.cfg"
  test -s "$out/vocab/vectors"
  test -s "$out/LICENSE"
  test -s "$out/LICENSES_SOURCES"
''
