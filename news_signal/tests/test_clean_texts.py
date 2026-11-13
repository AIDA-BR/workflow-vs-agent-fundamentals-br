import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import clean_texts as ct  # noqa: E402
import lexicon  # noqa: E402

BODY = "A Petrobras informou ao mercado que vai investir mais em exploração no próximo ano. " * 8


def test_remove_lista_de_leia_tambem_e_mantem_o_texto_seguinte():
    text = "\n".join(
        [
            BODY,
            "Leia também:",
            "- Petrobras tem produção recorde e triplica lucro",
            "- Vale anuncia dividendos extraordinários",
            "",
            "A estatal disse que a perfuração foi retomada em março.",
        ]
    )
    cleaned = ct.clean_text(text)
    assert "triplica lucro" not in cleaned and "dividendos extraordinários" not in cleaned
    assert "perfuração foi retomada" in cleaned


def test_lista_com_hifen_duplo_sai():
    cleaned = ct.clean_text(BODY + "\n- - Petrobras descobre petróleo em Marlim Sul\nFim do texto.")
    assert "Marlim Sul" not in cleaned


def test_corta_no_rodape():
    cleaned = ct.clean_text(BODY + "\nMais lidas\nReceita de sopa para o inverno.")
    assert "sopa" not in cleaned


def test_remove_publicidade_sem_cortar():
    cleaned = ct.clean_text(
        BODY + "\nContinua depois da publicidade\nO conselho aprovou o pagamento."
    )
    assert "publicidade" not in cleaned and "conselho aprovou" in cleaned


def test_texto_curto_depois_da_limpeza_vira_sem_texto():
    assert ct.clean_text("Leia também:\n- Uma manchete\n- Outra manchete") is None


def test_citacao_por_ticker_de_outra_classe():
    assert ct.count_mentions("PETR3 sobe 2% no pregão", "PETR4") == 1


def test_vale_homonimos_nao_contam():
    assert ct.count_mentions("Enchente no Alto Vale e no Vale do Itajaí", "VALE3") == 0
    assert ct.count_mentions("Vale a pena investir? Vale lembrar que...", "VALE3") == 0
    assert ct.count_mentions("Indígenas do Vale do Javari debatem", "VALE3") == 0
    assert ct.count_mentions("A Vale anunciou dividendos; VALE3 sobe", "VALE3") == 2


def test_equatorial_e_auren_homonimos():
    assert ct.count_mentions("Petrobras perfura na Margem Equatorial", "EQTL3") == 0
    assert ct.count_mentions("A Equatorial Energia comprou a Sabesp", "EQTL3") == 1
    assert ct.count_mentions("investidor Auren Hoffman criou a Dialog", "AURE3") == 0


def test_lexicon_separa_grupos_e_ignora_acentos():
    hits = lexicon.match(
        "Ibama multa Petrobras por vazamento de óleo; licença de perfuração suspensa"
    )
    assert hits["incidente_sancao"] >= 2 and hits["licenciamento"] == 1
    assert lexicon.match("Vazamento de energia elétrica dentro de casa") == {}
    assert lexicon.match("Petrobras aposta em descarbonização e créditos de carbono") == {
        "transicao": 2
    }
