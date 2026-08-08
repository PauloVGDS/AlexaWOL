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

## O teste

Copie `tools/wol_test.py` para **outro dispositivo da mesma rede** — um notebook, ou o celular
com Termux. Ele não tem dependências, só a biblioteca padrão do Python.

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

É o BIOS. Reinicie e entre no setup procurando por:

- **Power On by PCI-E / PCI** → Enabled
- **Wake on LAN / Resume by LAN** → Enabled
- **ErP Ready / EuP** → **Disabled** (quando ligado, corta a energia da placa de rede no S5)
- **Deep Sleep / Deep Sx** → Disabled

O `ErP Ready` é o culpado mais frequente e o menos óbvio, porque o nome não menciona rede.

## Se nem o S3 funciona

Verifique se o outro dispositivo está mesmo na sub-rede `192.168.1.0/24` e se o roteador não
tem isolamento de clientes ("AP isolation") ativo na rede Wi-Fi — ele bloqueia broadcast entre
Wi-Fi e cabo. É o mesmo requisito que a Echo precisará cumprir depois.

## Próximo passo

Só siga para [setup-hivemq.md](setup-hivemq.md) depois que o PC acordar nos dois estados —
ou pelo menos no S3, aceitando que "desligar" vai virar "suspender".
