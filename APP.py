import streamlit as st
import pandas as pd
import unicodedata
from datetime import datetime
import os
import re

# ________________________________
# CONFIGURAÇÃO DA PÁGINA STREAMLIT
# ________________________________
st.set_page_config(
    page_title="TH VARIEDADES | Gestão & Estoque",
    page_icon="📦",
    layout="wide"
)

ARQUIVO_ESTOQUE = "estoque.csv"
ARQUIVO_VENDAS = "vendas.csv"

# ________________________________
# FUNÇÕES AUXILIARES DE DADOS
# ________________________________
def normalizar_texto(texto):
    """Remove acentos, espaços extras e converte para minúsculas"""
    return ''.join(
        c for c in unicodedata.normalize('NFD', str(texto))
        if unicodedata.category(c) != 'Mn'
    ).lower().strip()

def limpar_nome_produto(nome):
    """Remove números soltos ou marcadores do início do nome"""
    nome_limpo = str(nome).strip()
    nome_limpo = re.sub(r'^\d+\s*(\(un\))?\s*(x)?\s*', '', nome_limpo, flags=re.IGNORECASE)
    return nome_limpo.strip()

def carregar_estoque():
    if os.path.exists(ARQUIVO_ESTOQUE):
        df = pd.read_csv(ARQUIVO_ESTOQUE, dtype={'sku': str, 'ultimo_pedido_id': str})
        if 'margem_porcentagem' not in df.columns:
            df['margem_porcentagem'] = 0.0
        return df
    else:
        return pd.DataFrame(columns=[
            'sku', 'nome_produto', 'quantidade_estoque', 
            'preco_custo_unitario', 'frete_unitario', 'custo_total_unitario', 
            'preco_venda_unitario', 'margem_porcentagem', 'ultimo_pedido_id'
        ])

def carregar_vendas():
    if os.path.exists(ARQUIVO_VENDAS):
        df = pd.read_csv(ARQUIVO_VENDAS, dtype={'sku': str, 'id_venda': str})
        if not df.empty and 'data_hora' in df.columns:
            df['data_hora_dt'] = pd.to_datetime(df['data_hora'], errors='coerce')
        return df
    else:
        return pd.DataFrame(columns=[
            'id_venda', 'sku', 'nome_produto', 'quantidade_vendida', 
            'preco_venda_praticado', 'custo_unitario', 'lucro_total_venda', 'data_hora'
        ])

def salvar_dados(df_estoque, df_vendas):
    if not df_estoque.empty:
        df_estoque['margem_porcentagem'] = df_estoque.apply(
            lambda row: round(((row['preco_venda_unitario'] - row['custo_total_unitario']) / row['custo_total_unitario']) * 100, 2)
            if row['custo_total_unitario'] > 0 else 0.0, axis=1
        )
    df_estoque_salvar = df_estoque.drop(columns=['data_hora_dt'], errors='ignore')
    df_vendas_salvar = df_vendas.drop(columns=['data_hora_dt'], errors='ignore')
    
    df_estoque_salvar.to_csv(ARQUIVO_ESTOQUE, index=False)
    df_vendas_salvar.to_csv(ARQUIVO_VENDAS, index=False)

def processar_csv_upload(uploaded_file, df_estoque):
    try:
        try:
            df_novo = pd.read_csv(uploaded_file, sep=',')
            if len(df_novo.columns) < 2:
                uploaded_file.seek(0)
                df_novo = pd.read_csv(uploaded_file, sep=';')
        except Exception:
            uploaded_file.seek(0)
            df_novo = pd.read_csv(uploaded_file, sep=';')

        df_novo.columns = [normalizar_texto(col) for col in df_novo.columns]
        
        colunas_necessarias = ['nome_produto', 'quantidade', 'preco_custo_unitario']
        for col in colunas_necessarias:
            if col not in df_novo.columns:
                st.error(f"❌ A coluna obrigatória **'{col}'** não foi encontrada no arquivo CSV.")
                return df_estoque, False, 0, 0.0

        df_novo['quantidade'] = pd.to_numeric(df_novo['quantidade'], errors='coerce').fillna(0).astype(int)
        df_novo['preco_custo_unitario'] = pd.to_numeric(
            df_novo['preco_custo_unitario'].astype(str).str.replace('R$', '', regex=False).str.replace(',', '.').str.strip(),
            errors='coerce'
        ).fillna(0.0)

        frete_total = 0.0
        if 'frete_total' in df_novo.columns:
            frete_val = pd.to_numeric(
                df_novo['frete_total'].astype(str).str.replace('R$', '', regex=False).str.replace(',', '.').str.strip(),
                errors='coerce'
            ).max()
            if pd.notna(frete_val):
                frete_total = float(frete_val)

        df_novo['valor_total_item'] = df_novo['quantidade'] * df_novo['preco_custo_unitario']

        subtotal = df_novo['valor_total_item'].sum()
        if subtotal > 0 and frete_total > 0:
            df_novo['peso_valor'] = df_novo['valor_total_item'] / subtotal
            df_novo['frete_unitario'] = (df_novo['peso_valor'] * frete_total) / df_novo['quantidade']
        else:
            df_novo['frete_unitario'] = 0.0

        df_novo['custo_total_unitario'] = df_novo['preco_custo_unitario'] + df_novo['frete_unitario']
        id_pedido = f"PED-{datetime.now().strftime('%Y%m%d%H%M%S')}"

        for _, row in df_novo.iterrows():
            nome_bruto = str(row['nome_produto'])
            nome = limpar_nome_produto(nome_bruto)
            
            qtd = row['quantidade']
            custo_unit = row['preco_custo_unitario']
            frete_unit = row['frete_unitario']
            custo_tot_unit = row['custo_total_unitario']
            
            preco_sugerido = round(custo_tot_unit * 2.50, 2)

            match_index = df_estoque[
                df_estoque['nome_produto'].apply(normalizar_texto) == normalizar_texto(nome)
            ].index

            if len(match_index) > 0:
                idx = match_index[0]
                qtd_antiga = df_estoque.at[idx, 'quantidade_estoque']
                custo_tot_antigo = df_estoque.at[idx, 'custo_total_unitario']

                qtd_nova_total = qtd_antiga + qtd
                novo_custo_medio = (
                    ((qtd_antiga * custo_tot_antigo) + (qtd * custo_tot_unit)) / qtd_nova_total
                    if qtd_nova_total > 0 else custo_tot_unit
                )

                df_estoque.at[idx, 'quantidade_estoque'] = qtd_nova_total
                df_estoque.at[idx, 'custo_total_unitario'] = round(novo_custo_medio, 2)
                
                if df_estoque.at[idx, 'preco_venda_unitario'] == 0.0:
                    df_estoque.at[idx, 'preco_venda_unitario'] = preco_sugerido
                
                df_estoque.at[idx, 'ultimo_pedido_id'] = id_pedido
            else:
                novo_sku = f"TH-{len(df_estoque) + 1:03d}"
                margem_inicial = round(((preco_sugerido - custo_tot_unit) / custo_tot_unit) * 100, 2) if custo_tot_unit > 0 else 0.0

                novo_item = {
                    'sku': novo_sku,
                    'nome_produto': nome,
                    'quantidade_estoque': qtd,
                    'preco_custo_unitario': round(custo_unit, 2),
                    'frete_unitario': round(frete_unit, 2),
                    'custo_total_unitario': round(custo_tot_unit, 2),
                    'preco_venda_unitario': preco_sugerido,
                    'margem_porcentagem': margem_inicial,
                    'ultimo_pedido_id': id_pedido
                }
                df_estoque = pd.concat([df_estoque, pd.DataFrame([novo_item])], ignore_index=True)

        return df_estoque, True, len(df_novo), frete_total
    except Exception as e:
        st.error(f"❌ Erro ao processar o arquivo: {e}")
        return df_estoque, False, 0, 0.0

# ________________________________
# CARREGAR DADOS
# ________________________________
df_estoque = carregar_estoque()
df_vendas = carregar_vendas()

# ________________________________
# INTERFACE GRÁFICA (SIDEBAR E NAVEGAÇÃO)
# ________________________________
st.sidebar.title("📦 Gestão de Vendas & PDV")
st.sidebar.markdown("---")

menu = st.sidebar.radio(
    "Navegação", 
    ["📊 Dashboard & KPIs", "📦 Estoque & Preços", "🛒 Registrar Venda", "📥 Importar Pedido (CSV)"],
    key="menu_principal_xz"
)

st.sidebar.markdown("---")

# ________________________________
# EXPORTAÇÃO DE ARQUIVOS CSV
# ________________________________
st.sidebar.subheader("📥 Exportar Dados")

csv_estoque = df_estoque.to_csv(index=False).encode('utf-8')
st.sidebar.download_button(
    label="📦 Exportar Estoque (estoque.csv)",
    data=csv_estoque,
    file_name="estoque.csv",
    mime="text/csv",
    use_container_width=True
)

csv_vendas = df_vendas.to_csv(index=False).encode('utf-8')
st.sidebar.download_button(
    label="🛒 Exportar Vendas (vendas.csv)",
    data=csv_vendas,
    file_name="vendas.csv",
    mime="text/csv",
    use_container_width=True
)

st.sidebar.markdown("---")

# ________________________________
# ZERAR DADOS COM VERIFICAÇÃO DE SENHA
# ________________________________
SENHA_CORRETA = "TVCHDF16*"

with st.sidebar.popover("⚠️ Zerar Todos os Dados"):
    st.warning("Atenção: Esta ação apaga permanentemente todos os registros de estoque e vendas!")
    senha_input = st.text_input("Digite a senha para confirmar:", type="password", key="input_senha_zerar")
    
    if st.button("Confirmar e Zerar Tudo", type="primary", use_container_width=True):
        if senha_input == SENHA_CORRETA:
            df_estoque_zerado = pd.DataFrame(columns=[
                'sku', 'nome_produto', 'quantidade_estoque', 
                'preco_custo_unitario', 'frete_unitario', 'custo_total_unitario', 
                'preco_venda_unitario', 'margem_porcentagem', 'ultimo_pedido_id'
            ])
            df_vendas_zerado = pd.DataFrame(columns=[
                'id_venda', 'sku', 'nome_produto', 'quantidade_vendida', 
                'preco_venda_praticado', 'custo_unitario', 'lucro_total_venda', 'data_hora'
            ])
            
            salvar_dados(df_estoque_zerado, df_vendas_zerado)
            st.success("Todos os dados foram zerados com sucesso!")
            st.rerun()
        else:
            st.error("❌ Senha incorreta! Os dados não foram alterados.")

# ________________________________
# ABA 1: DASHBOARD & KPIS
# ________________________________
if menu == "📊 Dashboard & KPIs":
    st.title("📊 Painel Geral de Vendas e Previsões")
    
    # --------------------------------
    # FILTROS DINÂMICOS
    # --------------------------------
    with st.expander("🔍 **Filtros do Dashboard**", expanded=True):
        f_col1, f_col2, f_col3 = st.columns(3)
        
        # Filtro de Produto
        produtos_disponiveis = ["Todos"] + sorted(list(set(
            df_estoque['nome_produto'].tolist() + df_vendas['nome_produto'].tolist()
        )))
        produto_sel = f_col1.selectbox("Filtrar por Produto:", produtos_disponiveis)
        
        # Filtro por Lote/Pedido
        lotes_disponiveis = ["Todos"] + sorted([l for l in df_estoque['ultimo_pedido_id'].dropna().unique() if str(l).strip() != ""])
        lote_sel = f_col2.selectbox("Filtrar por Lote/Pedido:", lotes_disponiveis)
        
        # Filtro por Data
        datas_filtro = f_col3.date_input("Filtrar por Intervalo de Datas (Vendas):", value=(), key="filtro_datas")

    # Aplicação dos Filtros nos DataFrames
    df_vendas_f = df_vendas.copy()
    df_estoque_f = df_estoque.copy()

    if produto_sel != "Todos":
        df_vendas_f = df_vendas_f[df_vendas_f['nome_produto'] == produto_sel]
        df_estoque_f = df_estoque_f[df_estoque_f['nome_produto'] == produto_sel]

    if lote_sel != "Todos":
        skus_do_lote = df_estoque[df_estoque['ultimo_pedido_id'] == lote_sel]['sku'].tolist()
        df_vendas_f = df_vendas_f[df_vendas_f['sku'].isin(skus_do_lote)]
        df_estoque_f = df_estoque_f[df_estoque_f['ultimo_pedido_id'] == lote_sel]

    if isinstance(datas_filtro, (list, tuple)) and len(datas_filtro) == 2:
        d_inicio, d_fim = datas_filtro
        if 'data_hora_dt' in df_vendas_f.columns:
            df_vendas_f = df_vendas_f[
                (df_vendas_f['data_hora_dt'].dt.date >= d_inicio) & 
                (df_vendas_f['data_hora_dt'].dt.date <= d_fim)
            ]

    # --------------------------------
    # CÁLCULO DOS KPIS FILTRADOS
    # --------------------------------
    faturamento_real = (df_vendas_f['quantidade_vendida'] * df_vendas_f['preco_venda_praticado']).sum() if not df_vendas_f.empty else 0.0
    lucro_real = df_vendas_f['lucro_total_venda'].sum() if not df_vendas_f.empty else 0.0
    custo_total_vendido = (df_vendas_f['quantidade_vendida'] * df_vendas_f['custo_unitario']).sum() if not df_vendas_f.empty else 0.0
    margem_real_pct = (lucro_real / custo_total_vendido * 100) if custo_total_vendido > 0 else 0.0
    
    prev_faturamento = (df_estoque_f['quantidade_estoque'] * df_estoque_f['preco_venda_unitario']).sum() if not df_estoque_f.empty else 0.0
    prev_custo_estoque = (df_estoque_f['quantidade_estoque'] * df_estoque_f['custo_total_unitario']).sum() if not df_estoque_f.empty else 0.0
    prev_lucro = prev_faturamento - prev_custo_estoque
    margem_estoque_pct = (prev_lucro / prev_custo_estoque * 100) if prev_custo_estoque > 0 else 0.0

    st.markdown("---")
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Faturamento Realizado", f"R$ {faturamento_real:.2f}")
    col2.metric("Lucro Realizado", f"R$ {lucro_real:.2f}")
    col3.metric("Prev. Faturamento (Estoque)", f"R$ {prev_faturamento:.2f}")
    col4.metric("Prev. Lucro Total (Estoque)", f"R$ {prev_lucro:.2f}")

    col_m1, col_m2 = st.columns(2)
    col_m1.metric("📈 % Margem de Lucro Real", f"{margem_real_pct:.2f}%")
    col_m2.metric("📦 % Margem de Lucro Projetada", f"{margem_estoque_pct:.2f}%")

    st.markdown("---")

    # --------------------------------
    # GRÁFICO NATIVO DO STREAMLIT (TOP 5 MAIS / MENOS VENDIDOS)
    # --------------------------------
    st.subheader("📊 Análise de Desempenho dos Produtos")
    
    if not df_vendas_f.empty:
        g_col1, g_col2 = st.columns([1, 3])
        
        with g_col1:
            st.markdown("##### Visualização")
            opcao_top = st.radio(
                "Filtrar Rank:", 
                options=["🔥 Top 5 Mais Vendidos", "❄️ Top 5 Menos Vendidos"],
                key="radio_top_produtos"
            )

        # Agrupamento dos dados
        vendas_agrupadas = df_vendas_f.groupby(['sku', 'nome_produto'])['quantidade_vendida'].sum().reset_index()
        vendas_agrupadas['Produto'] = vendas_agrupadas['sku'] + " - " + vendas_agrupadas['nome_produto']
        
        is_top = "Mais" in opcao_top
        vendas_agrupadas = vendas_agrupadas.sort_values(
            by='quantidade_vendida', 
            ascending=not is_top
        ).head(5)

        # Prepara estrutura para gráfico de barras do Streamlit
        chart_data = vendas_agrupadas.set_index('Produto')[['quantidade_vendida']]
        chart_data.columns = ['Qtd. Vendida']

        with g_col2:
            st.bar_chart(chart_data, color="#0066CC" if is_top else "#FF4B4B")
    else:
        st.info("Nenhum dado de venda disponível no momento para gerar o gráfico.")

    st.markdown("---")
    st.subheader("📋 Histórico Recente de Vendas")
    if not df_vendas_f.empty:
        df_exibicao = df_vendas_f.drop(columns=['data_hora_dt'], errors='ignore')
        st.dataframe(df_exibicao.sort_values(by="data_hora", ascending=False), use_container_width=True)
    else:
        st.info("Nenhuma venda encontrada para os filtros selecionados.")

# ________________________________
# ABA 2: ESTOQUE E PREÇOS
# ________________________________
elif menu == "📦 Estoque & Preços":
    st.title("📦 Gerenciamento de Estoque e Margens")
    
    if not df_estoque.empty:
        st.caption("💡 Edite os valores na tabela e clique no botão **Salvar Alterações nos Preços** para confirmar.")

        df_display = df_estoque.copy()
        df_display['margem_porcentagem'] = df_display.apply(
            lambda row: round(((row['preco_venda_unitario'] - row['custo_total_unitario']) / row['custo_total_unitario']) * 100, 2)
            if row['custo_total_unitario'] > 0 else 0.0, axis=1
        )

        edited_df = st.data_editor(
            df_display,
            column_config={
                "sku": st.column_config.TextColumn("SKU", disabled=True),
                "nome_produto": st.column_config.TextColumn("Produto", disabled=True),
                "quantidade_estoque": st.column_config.NumberColumn("Estoque Atual", disabled=True),
                "preco_custo_unitario": st.column_config.NumberColumn("Custo Nota (R$)", disabled=True, format="R$ %.2f"),
                "frete_unitario": st.column_config.NumberColumn("Frete Unit. (R$)", disabled=True, format="R$ %.2f"),
                "custo_total_unitario": st.column_config.NumberColumn("Custo Total (R$)", disabled=True, format="R$ %.2f"),
                "preco_venda_unitario": st.column_config.NumberColumn("Preço de Venda (R$)", min_value=0.0, format="R$ %.2f"),
                "margem_porcentagem": st.column_config.NumberColumn("% Margem Lucro", disabled=True, format="%.2f %%"),
                "ultimo_pedido_id": st.column_config.TextColumn("Lote Pedido", disabled=True)
            },
            hide_index=True,
            use_container_width=True,
            key="tabela_editor_interativo"
        )

        if st.button("💾 Salvar Alterações nos Preços", use_container_width=True):
            salvar_dados(edited_df, df_vendas)
            st.toast("Preços e margens salvos com sucesso!", icon="✅")
            st.rerun()
    else:
        st.info("O estoque está vazio. Importe um pedido em CSV para começar.")

# ________________________________
# ABA 3: REGISTRAR VENDA (PDV)
# ________________________________
elif menu == "🛒 Registrar Venda":
    st.title("🛒 Baixa Rápida de Venda")
    
    if not df_estoque.empty:
        df_disponivel = df_estoque[df_estoque['quantidade_estoque'] > 0]
        
        if not df_disponivel.empty:
            lista_produtos = df_disponivel.apply(lambda x: f"{x['sku']} - {x['nome_produto']} (Estoque: {x['quantidade_estoque']})", axis=1)
            
            produto_selecionado = st.selectbox("Selecione ou digite o nome/SKU do produto:", lista_produtos)
            sku_selecionado = produto_selecionado.split(" - ")[0]
            
            item = df_estoque[df_estoque['sku'] == sku_selecionado].iloc[0]
            
            col_a, col_b = st.columns(2)
            with col_a:
                qtd_venda = st.number_input("Quantidade Vendida:", min_value=1, max_value=int(item['quantidade_estoque']), value=1)
            with col_b:
                preco_venda_input = st.number_input("Preço Praticado por Unidade (R$):", min_value=0.0, value=float(item['preco_venda_unitario']))

            lucro_estimado = (preco_venda_input - item['custo_total_unitario']) * qtd_venda
            st.info(f"💰 Lucro total nesta transação: **R$ {lucro_estimado:.2f}**")

            if st.button("✅ Confirmar Venda", use_container_width=True):
                idx = df_estoque[df_estoque['sku'] == sku_selecionado].index[0]
                
                df_estoque.at[idx, 'quantidade_estoque'] -= qtd_venda
                
                nova_venda = {
                    'id_venda': f"VENDA-{len(df_vendas)+1:04d}",
                    'sku': sku_selecionado,
                    'nome_produto': item['nome_produto'],
                    'quantidade_vendida': qtd_venda,
                    'preco_venda_praticado': preco_venda_input,
                    'custo_unitario': item['custo_total_unitario'],
                    'lucro_total_venda': round(lucro_estimado, 2),
                    'data_hora': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                }
                df_vendas = pd.concat([df_vendas, pd.DataFrame([nova_venda])], ignore_index=True)
                
                salvar_dados(df_estoque, df_vendas)
                st.toast(f"Venda de {qtd_venda}x '{item['nome_produto']}' registrada!", icon="🎉")
                st.rerun()
        else:
            st.warning("⚠️ Todos os produtos cadastrados estão com o estoque zerado.")
    else:
        st.info("Nenhum produto cadastrado no estoque.")

# ________________________________
# ABA 4: IMPORTAR PEDIDO (CSV)
# ________________________________
elif menu == "📥 Importar Pedido (CSV)":
    st.title("📥 Importar Pedido de Fornecedor")
    st.caption("Suba o arquivo CSV com a lista de compras para atualizar seu estoque automaticamente.")
    
    arquivo_upload = st.file_uploader("Selecione o arquivo CSV do pedido", type=["csv"])
    
    if arquivo_upload is not None:
        if st.button("🚀 Processar Pedido", use_container_width=True):
            with st.spinner("Processando itens e calculando rateio de frete..."):
                df_estoque, sucesso, qtd_itens, frete = processar_csv_upload(arquivo_upload, df_estoque)
                
            if sucesso:
                salvar_dados(df_estoque, df_vendas)
                st.success("✅ Pedido processado e adicionado ao estoque!")
                st.toast("Estoque atualizado com sucesso!", icon="📦")
                
                c1, c2 = st.columns(2)
                c1.metric("Itens Processados", qtd_itens)
                c2.metric("Frete Rateado Detectado", f"R$ {frete:.2f}")
                
                st.balloons()
