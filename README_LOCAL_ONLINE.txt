CENTRAL CT-e / DACTE - R12.13.10 LOCAL + ONLINE
================================================

OBJETIVO
- Rodar a Central no próprio PC Windows.
- Criar um endereço HTTPS temporário *.trycloudflare.com para acesso pela internet.
- Não precisa de VPS.

COMO USAR
1. Extraia este ZIP para uma pasta normal, por exemplo:
   C:\CentralCTe
2. Dê dois cliques em:
   00_INICIAR_LOCAL_ONLINE.bat
3. No primeiro uso, o navegador abrirá em http://127.0.0.1:8765.
   Crie o primeiro usuário; ele será criado automaticamente como Desenvolvedor.
4. Volte à janela do inicializador e pressione ENTER.
5. O programa baixa automaticamente o cloudflared oficial se necessário.
6. Será criado um link HTTPS temporário terminado em trycloudflare.com.
   O link também fica salvo em URL_ONLINE.txt.

PARA DESLIGAR
- Execute 00_PARAR_LOCAL_ONLINE.bat

IMPORTANTE
- O PC precisa ficar ligado para o endereço online funcionar.
- O link trycloudflare.com é temporário e pode mudar a cada inicialização.
- Os dados e usuários ficam em web_local\data neste computador.
- Este pacote não inclui os usuários atuais da antiga VPS.
- Para trazer usuários/dados antigos, restaure o backup de /data antes de usar.

VERSÃO
- Aplicação: RC27.14 WEB/WINDOWS MVP13 R12.13.10
- Motor comercial: RC26.6


R12.13.10 - 04/09/2026
- Primeiro cadastro de uma instalação nova passa a ser sempre perfil Desenvolvedor.
- Tela de Primeiro acesso deixa de criar Administrador.
- O Desenvolvedor inicial recebe imediatamente as permissões de governança, usuários, segurança e recursos técnicos.
- Usuários já existentes não são alterados automaticamente.
- Motor comercial continua RC26.6.


R12.13.6 - 31/08/2026
- Corrige falso PARCEIRO SEM CADASTRO da GRAUNA_TRANSPORTES no pacote Local + Online.
- Tabela compilada passa a ser sincronizada automaticamente no startup/workspace.
- Nova sincronização obrigatória imediatamente antes de cada validação XML.
- Sincronização deixa de depender da abertura da tela de Desenvolvedor.
- Mantém regras Graúna: Redenção 28%, mínimo da rota, Atacadão explícito 40%, >120 kg somente shadow.
- Mantém hotfix do Cloudflare Quick Tunnel.



R12.13.9 - 01/09/2026
- Corrige bloqueio da prévia/PDF assinado quando um CT-e divergente foi baixado manualmente com justificativa.
- A baixa manual aprovada não apaga a divergência automática: o PDF mostra o cálculo original, a diferença e o status OK MANUAL.
- Justificativa, responsável e data da aprovação são reanexados à fotografia oficial do DACTE, inclusive em registros antigos.
- Se um CT-e baixado manualmente não possuía bloco compacto, o sistema cria um bloco de auditoria antes do PDF.
- O guarda final continua bloqueando falso OK automático sem decisão manual.

R12.13.7 - 31/08/2026
- Corrige falsos DIVERGENTE da AC LOG / C VARGAS quando a tabela possui percentual, frete-peso e mínimo simultaneamente.
- Regra oficial C Vargas passa a usar o MAIOR valor entre percentual da rota, frete-peso e frete mínimo.
- Preserva componentes opcionais (GRIS/pedágio) somente quando efetivamente cobrados no XML.
- Matriz real do relatório 31/08: 33/33 CT-es C Vargas conferem com a regra híbrida.
- No lote de 86 CT-es, a expectativa após reprocessar é 84 aprovados e somente 2 em atenção por regra W S não encontrada.
- Motor comercial continua RC26.6.

R12.13.9 - correção adicional de 01/09/2026
- Corrige definitivamente o caminho de lote/prévia ASSINADA para CT-es com baixa manual.
- Consolida decisões manuais antigas antes do render e cria o bloco compacto antes da assinatura.
- Justificativa, responsável e data ficam explícitos no PDF quando o bloco compacto estiver habilitado.
- O launcher detecta processo antigo na porta 8765 e o reinicia se a versão em memória estiver desatualizada.
- Para atualizar uma instalação existente, pare/inicie o Central após aplicar o hotfix; o instalador R12.13.9 também força essa parada.
