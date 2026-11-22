# Grafo do Noema como trilha de estudo

## Plano

1. **Contrato e criação:** confirmar o uso dos schemas da API; adicionar `plan`,
   `level` e `weight` somente como campos compatíveis com payloads antigos.
   Versionar o novo prompt e fornecer SQL de atualização do agente, sem alterar
   o banco nesta entrega.
2. **Qualidade na geração:** fazer o app importar pesos antigos como `1.0`,
   reparar apenas defeitos determinísticos (pré-requisitos em contêineres,
   ciclos, transitividade, duplicatas e auto-laços) e expor avisos estruturados.
   Problemas sem reparo seguro são enviados em uma única tentativa corretiva.
   Converter SUBTOPIC pai→filho da criação para o sentido legado persistido
   (filho→pai), sem alterar grafos já armazenados.
3. **Trilha de aprendizagem:** calcular progresso de contêineres pelas folhas,
   respeitar somente pré-requisitos essenciais para prontidão, manter a abertura
   livre e ordenar recomendações por revisão vencida, camada topológica,
   impacto downstream e título.
4. **Experiência de uso:** mostrar lacunas com ações de continuar ou revisar,
   não recomendar contêineres e não gerar pacotes de estudo para eles.
5. **Verificação:** cobrir contratos e reparos com pytest/Dart; adicionar um
   verificador Python de qualidade de grafos JSON; executar as suítes disponíveis.

## Restrições e verificação

Sem novos tipos de tarefa/agentes, alterações de estrutura do grafo, migrações,
novas tabelas ou mudanças no FSRS. `GraphNode.level` é transitório; `weight`
usa a coluna existente. O repositório não contém o JSON do grafo de exemplo nem
seu tema completo; portanto, métricas comparáveis antes/depois dependem do
fornecimento desse fixture e não devem ser inventadas.
