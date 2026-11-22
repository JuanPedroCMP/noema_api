# Grafo do Noema como trilha de estudo

## Plano

1. **Contrato e criação:** confirmar o uso dos schemas da API; adicionar `plan`,
   `level`, `weight` e objetivos concisos por folha como campos opcionais
   compatíveis com payloads antigos. Reutilizar `graph_node.description`, sem
   migração. Versionar o prompt e fornecer SQL de atualização do agente.
2. **Qualidade na geração:** fazer o app importar pesos antigos como `1.0`,
   reparar defeitos determinísticos e devolver esses reparos como feedback.
   Validar também a árvore de contenção, níveis de aprendizagem e caminhos a
   partir de foundations; reduzir transitividade somente através de caminhos
   essenciais. Enviar códigos e IDs em uma única tentativa corretiva e manter
   avisos restantes visíveis. Converter SUBTOPIC pai→filho da criação para o
   sentido legado persistido (filho→pai), sem alterar grafos já armazenados.
3. **Trilha de aprendizagem:** calcular progresso de contêineres pelas folhas,
   respeitar somente pré-requisitos essenciais para prontidão, manter a abertura
   livre e ordenar recomendações por revisão vencida, camada topológica,
   impacto downstream e título.
4. **Experiência de uso:** mostrar lacunas com ações de continuar ou revisar,
   não recomendar contêineres e não gerar pacotes de estudo para eles.
5. **Verificação:** cobrir contratos e reparos com pytest/Dart; adicionar um
   verificador Python de qualidade de grafos JSON, incluindo hierarquia e pesos;
   executar as suítes disponíveis.

## Restrições e verificação

Sem novos tipos de tarefa/agentes, alterações de estrutura do grafo, migrações,
novas tabelas ou mudanças no FSRS. `GraphNode.level` é transitório; `weight`
usa a coluna existente. O repositório não contém o JSON do grafo de exemplo nem
seu tema completo; portanto, métricas comparáveis antes/depois dependem do
fornecimento desse fixture e não devem ser inventadas.
