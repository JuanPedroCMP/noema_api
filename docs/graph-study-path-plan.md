# Grafo do Noema como trilha de estudo

## Plano

1. **Planejamento e criação em etapas:** usar o mesmo agente e a mesma
   `TaskType` com dois modos de resposta: `MODE: PLAN` produz um blueprint
   tipado de escopo, pressupostos, conhecimento prévio, resultados observáveis,
   evidências de avaliação e dependências entre resultados; `MODE: CREATE`
   constrói o grafo exclusivamente a partir desse blueprint. O contrato final
   vincula cada resultado pelo `outcome_id` aos nós folha que o ensinam.
   Validar IDs, referências e ciclos no blueprint antes de gerar o grafo e
   conferir que cada dependência planejada tem um caminho essencial no grafo.
   Mostrar e exigir a confirmação do blueprint antes da segunda chamada; uma
   edição do pedido invalida o plano. Mostrar cobertura e grafo na prévia final.
   Não criar agente, tarefa, tabela ou migração.
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
   impacto downstream e título. Para o nó selecionado, exibir a sequência
   transitiva de pré-requisitos essenciais ainda não prontos, em ordem de camada
   (foundations antes de intermediários), impacto e título; arestas fracas ficam
   como sugestões. No início, destacar a foundation recomendada com maior
   impacto, sem impor prazo total ou limitar o tamanho da trilha.
4. **Experiência de uso:** mostrar lacunas com ações de continuar ou revisar,
   não recomendar contêineres e não gerar pacotes de estudo para eles.
5. **Verificação:** cobrir contrato e DAG do blueprint, seleção dos modos de
   resposta e a sequência ponta a ponta PLAN → CREATE com pytest/Dart; adicionar um
   verificador Python de qualidade de grafos JSON, incluindo hierarquia e pesos;
   executar as suítes disponíveis.

## Restrições e verificação

Sem novos tipos de tarefa/agentes, alterações de estrutura do grafo, migrações,
novas tabelas ou mudanças no FSRS. `GraphNode.level` é transitório; `weight`
usa a coluna existente. O repositório não contém o JSON do grafo de exemplo nem
seu tema completo; portanto, métricas comparáveis antes/depois dependem do
fornecimento desse fixture e não devem ser inventadas.
