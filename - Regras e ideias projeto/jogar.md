# AUTOMAÇÃO NO SITE DA CAIXA
DIGITAR NO CONSOLE
```
allow pasting

```
E depois usar pra automatizar os jogos no site na LOTERIA CAIXA

```
////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////

// Lista de jogos (adicione mais se quiser)
let jogos = [
[1, 2, 4, 5, 6, 7, 9, 12, 13, 17, 18, 20, 21, 22, 24],
[1, 4, 5, 6, 7, 9, 10, 12, 13, 15, 16, 17, 18, 20, 21],
[1, 4, 5, 6, 7, 9, 12, 13, 14, 17, 18, 20, 21, 22, 23]
];

async function jogarAutomatico(jogos) {
  for (let i = 0; i < jogos.length; i++) {
    const jogo = jogos[i];

    console.log(`🎯 Jogando jogo ${i + 1}/${jogos.length}:`, jogo.join(", "));

    // Limpa o volante
    let limparBtn = document.getElementById("limparvolante");
    if (limparBtn) limparBtn.click();
    else console.warn("⚠️ Botão 'Limpar Volante' não encontrado.");

    // Espera o volante limpar
    await new Promise(r => setTimeout(r, 500));

    // Seleciona os números
    for (let num of jogo) {
      let id = "n" + String(num).padStart(2, "0");
      let el = document.getElementById(id);
      if (el) {
        el.click();
        await new Promise(r => setTimeout(r, 100)); // pequeno atraso entre cliques
      } else {
        console.warn("Número não encontrado:", id);
      }
    }

    // Espera um pouco antes de colocar no carrinho
    await new Promise(r => setTimeout(r, 300));

    // Clica no botão de colocar no carrinho
    let carrinhoBtn = document.getElementById("colocarnocarrinho");
    if (carrinhoBtn) {
      carrinhoBtn.click();
      console.log(`🛒 Jogo ${i + 1} colocado no carrinho.`);
    } else {
      console.warn("⚠️ Botão 'Colocar no carrinho' não encontrado.");
    }

    // Espera 2 segundos antes do próximo jogo
    await new Promise(r => setTimeout(r, 2000));
  }

  console.log("✅ Todos os jogos foram processados automaticamente!");
}

// Executa automaticamente
jogarAutomatico(jogos);

////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////
```

AGORA PRA AUTOMATIZAR NO SITE DA LOTOSPOT

```
// Lista das dezenas que você quer selecionar automaticamente
// Altere conforme desejar
const dezenasParaSelecionar = ['01','02','04','05','07','09','10','11','12','14','20','21','22','24','25'];

// Procura todos os botões que representam dezenas
const botoes = document.querySelectorAll('.box-dezenas-selecionador button');

// Função auxiliar para clicar em um botão específico
function clicarDezena(numero) {
  const numeroFormatado = numero.toString().padStart(2, '0');
  const botao = Array.from(botoes).find(b => b.textContent.trim().startsWith(numeroFormatado));
  if (botao) {
    botao.click();
    console.log(`✅ Selecionado: ${numeroFormatado}`);
  } else {
    console.warn(`⚠️ Botão ${numeroFormatado} não encontrado`);
  }
}

// Clica em cada número da lista
dezenasParaSelecionar.forEach(num => clicarDezena(num));

```