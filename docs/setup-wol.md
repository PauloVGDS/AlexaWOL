# 1. Validar o Wake-on-LAN

**Faça isto antes de qualquer outra coisa.** Se o PC não acorda com um magic packet enviado
da própria rede, nenhuma skill vai fazê-lo acordar. Este teste separa "problema de hardware"
de "problema de software", e é o que evita depurar três camadas ao mesmo tempo.

## O que já está pronto nesta máquina

Levantado com `Get-NetAdapterAdvancedProperty` e `powercfg`:

| Item | Estado |
|---|---|
| Interface | `Ethernet 3` — Realtek PCIe GbE, **cabeada** |
| MAC | `00-11-22-33-44-55` |
| `Wake on Magic Packet` | Enabled |
| `Shutdown Wake-On-Lan` | Enabled |
| Placa em `wake_armed` | Sim |
| Fast Startup | **Desativado** |
| Estados | S3 (Espera) e Hibernar |

Nada a mudar no Windows. Se um dia algo parar de funcionar, confira estes mesmos pontos:

```powershell
Get-NetAdapterAdvancedProperty -Name 'Ethernet 3' |
    Where-Object DisplayName -match 'Wake|Shutdown'
powercfg /devicequery wake_armed
(Get-ItemProperty 'HKLM:\SYSTEM\CurrentControlSet\Control\Session Manager\Power').HiberbootEnabled
```

`HiberbootEnabled` precisa ser `0`. O Fast Startup é a causa mais comum de "o WOL funciona
quando suspendo, mas não quando desligo".

## Antes de testar: o BIOS — **isto é requisito, não sugestão**

Na maioria das placas, **o Windows sozinho não basta**. As opções do driver controlam o
comportamento do sistema operacional; quem decide se a placa de rede continua energizada com a
máquina desligada é o firmware. E a configuração de fábrica costuma cortar essa energia.

Nesta instalação o "ligar" só passou a funcionar **depois** de mexer no BIOS, mesmo com tudo
correto do lado do Windows.

Reinicie, entre no setup e procure:

| Opção | Valor | Observação |
|---|---|---|
| **Power On by PCI-E / PCI** | Enabled | Às vezes aparece como *Wake on LAN* ou *Resume by LAN* |
| **ErP Ready / EuP** | **Disabled** | O culpado mais frequente — e o nome não menciona rede |
| **Deep Sleep / Deep Sx** | Disabled | Presente sobretudo em placas Intel e notebooks |

O **ErP** merece destaque: é um modo de baixo consumo para conformidade energética que corta a
alimentação de tudo no S5, inclusive da placa de rede. Habilitado, nenhuma configuração do
Windows faz o WOL funcionar a partir do desligamento.

Os nomes variam bastante por fabricante. Se não achar nada parecido, procure o manual da sua
placa-mãe por "Wake on LAN".

Se você quiser adiar isso: suspender (S3) geralmente funciona **sem** mexer no BIOS, porque a
placa continua energizada nesse estado. Desligar (S5) é que exige.

## Como enviar o magic packet

O pacote precisa sair de **outro dispositivo da mesma rede** — o PC alvo obviamente não pode
acordar a si mesmo. Três caminhos, do mais fácil ao mais trabalhoso:

**Pelo roteador.** Boa parte da linha Archer da TP-Link tem Wake-on-LAN embutido, em
**Avançado → Rede → Wake-on-LAN**. Entre em <http://192.168.1.1> e procure. Não instala nada
e é o caminho mais rápido — vale olhar antes de qualquer outra coisa.

**Pelo celular.** Qualquer app gratuito de "Wake on LAN" na Play Store ou App Store. Preencha
o MAC `00-11-22-33-44-55` e o broadcast `192.168.1.255`. O celular precisa estar no Wi-Fi da
casa, não em dados móveis.

**Por outro computador.** Copie `tools/wol_test.py` para lá. Ele não tem dependências, só a
biblioteca padrão do Python.

### Do estado suspenso (S3)

1. No PC: `rundll32.exe powrprof.dll,SetSuspendState 0,1,0`
2. Do outro dispositivo:

```bash
python wol_test.py 00-11-22-33-44-55
```

Se não funcionar, tente o broadcast da sub-rede em vez do global:

```bash
python wol_test.py 00-11-22-33-44-55 --broadcast 192.168.1.255
```

### Do estado desligado (S5)

Desligue o PC normalmente e repita. Este é o caso que depende do BIOS.

## Se o S3 funciona mas o S5 não

É o BIOS — volte à seção do começo deste documento. Esse é exatamente o sintoma de placa de
rede sem energia no desligamento, e quase sempre se resolve desabilitando o **ErP Ready**.

## Se nem o S3 funciona

Verifique se o outro dispositivo está mesmo na sub-rede `192.168.1.0/24` e se o roteador não
tem isolamento de clientes ("AP isolation") ativo na rede Wi-Fi — ele bloqueia broadcast entre
Wi-Fi e cabo. É o mesmo requisito que a Echo precisará cumprir depois.

## Por que vale gastar esses dois minutos

Sem este teste, se o "Alexa, ligar o computador" falhar depois, você não sabe se o problema é
BIOS, placa de rede, a Echo, o token do account linking ou o event gateway. São cinco
suspeitos. Com o teste feito, sobra um.

Se você preferir ir direto ao teste com a voz, dá para isolar pelo log — o `events.py` registra
a resposta do gateway:

```powershell
aws logs tail /aws/lambda/alexawol --follow --region us-east-1
```

`event gateway respondeu 202` significa que o lado da Alexa fez tudo certo e a Echo recebeu
ordem de transmitir; se mesmo assim o PC não acordar, o problema é local e na prática é BIOS.
Sem o 202, é token ou configuração. Sem invocação nenhuma no log, é a permissão do Lambda.

## Próximo passo

Só siga para [setup-hivemq.md](setup-hivemq.md) depois que o PC acordar nos dois estados —
ou pelo menos no S3, aceitando que "desligar" vai virar "suspender".
