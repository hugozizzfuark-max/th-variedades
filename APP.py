import streamlit as st
import pandas as pd
import unicodedata
from datetime import datetime
import os
import re

# =========================================================
# CONFIGURAÇÃO DA PÁGINA STREAMLIT
# =========================================================
st.set_page_config(
    page_title="TH Variedades - Gestão & Estoque",
    page_icon="🛍️",
    layout="wide"
)

ARQUIVO_ESTOQUE = "estoque.csv"
ARQUIVO_VENDAS = "vendas.csv"

# =========================================================
# FUNÇÕES AUXILIARES DE DADOS
# =========================================================
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
        df = pd.read_csv(ARQUIVO_ESTOQUE)
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
        return pd.read_csv(ARQUIVO_VENDAS)
    else:
        return pd.DataFrame(columns=[
            'id_venda', 'sku', 'nome_produto', 'quantidade_vendida', 
            'preco_venda_praticado', 'custo_unitario', 'lucro_total_venda', 'data_hora'
        ])

def salvar_dados(df_estoque, df_vendas):
    # Recalcular margem % em relação ao Custo Total (Lucro / Custo Total * 100)
    if not df_estoque.empty:
        df_estoque['margem_porcentagem'] = df_estoque.apply(
            lambda row: round(((row['preco_venda_unitario'] - row['custo_total_unitario']) / row['custo_total_unitario']) * 100, 2)
            if row['custo_total_unitario'] > 0 else 0.0, axis=1
        )
    df_estoque.to_csv(ARQUIVO_ESTOQUE, index=False)
    df_vendas.to_csv(ARQUIVO_VENDAS, index=False)

def processar_csv_upload(uploaded_file, df_estoque):
    try:
        try:
            df_novo = pd.read_csv(uploaded_file, sep=',')
            if len(df_novo.columns) < 2:
                uploaded_file.seek(0)
                df_novo = pd.read_csv(uploaded_file, sep=';')
        except:
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
            
            # PREÇO SUGERIDO (Custo Total + 150% de Lucro sobre o custo)
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
                
                # Porcentagem de margem calculada sobre o custo total
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

# =========================================================
# CARREGAR DADOS
# =========================================================
df_estoque = carregar_estoque()
df_vendas = carregar_vendas()

# =========================================================
# INTERFACE GRÁFICA (SIDEBAR E NAVEGAÇÃO)
# =========================================================
st.sidebar.title("🛍️ TH Variedades")
st.sidebar.markdown("---")

menu = st.sidebar.radio(
    "Navegação", 
    ["📊 Dashboard & KPIs", "📦 Estoque & Preços", "🛒 Registrar Venda", "📥 Importar Pedido (CSV)"],
    key="menu_principal_th"
)

st.sidebar.markdown("---")

# BOTÃO PARA ZERAR OS DADOS
if st.sidebar.button("⚠️ Zerar Todos os Dados", key="btn_zerar_dados"):
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
    st.sidebar.success("Todos os dados foram zerados!")
    st.rerun()

# ---------------------------------------------------------
# ABA 1: DASHBOARD & KPIS
# ---------------------------------------------------------
if menu == "📊 Dashboard & KPIs":
    st.title("📊 Painel Geral de Vendas e Previsões")
    
    # 1. Faturamento e Lucro Realizado
    faturamento_real = (df_vendas['quantidade_vendida'] * df_vendas['preco_venda_praticado']).sum() if not df_vendas.empty else 0.0
    lucro_real = df_vendas['lucro_total_venda'].sum() if not df_vendas.empty else 0.0
    custo_total_vendido = (df_vendas['quantidade_vendida'] * df_vendas['custo_unitario']).sum() if not df_vendas.empty else 0.0
    margem_real_pct = (lucro_real / custo_total_vendido * 100) if custo_total_vendido > 0 else 0.0
    
    # 2. Previsão de Faturamento e Lucro (Estoque)
    prev_faturamento = (df_estoque['quantidade_estoque'] * df_estoque['preco_venda_unitario']).sum() if not df_estoque.empty else 0.0
    prev_custo_estoque = (df_estoque['quantidade_estoque'] * df_estoque['custo_total_unitario']).sum() if not df_estoque.empty else 0.0
    prev_lucro = prev_faturamento - prev_custo_estoque
    margem_estoque_pct = (prev_lucro / prev_custo_estoque * 100) if prev_custo_estoque > 0 else 0.0
    
    # Linha 1 de Cartões: R$ Faturamento e Lucro
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Faturamento Realizado", f"R$ {faturamento_real:.2f}")
    col2.metric("Lucro Realizado", f"R$ {lucro_real:.2f}")
    col3.metric("Prev. Faturamento (Estoque)", f"R$ {prev_faturamento:.2f}")
    col4.metric("Prev. Lucro Total (Estoque)", f"R$ {prev_lucro:.2f}")

    # Linha 2 de Cartões: % Margem de Lucro sobre Custo
    col_m1, col_m2 = st.columns(2)
    col_m1.metric("📈 % Margem de Lucro Real (Até o momento)", f"{margem_real_pct:.2f}%")
    col_m2.metric("📦 % Margem de Lucro Total (Estoque Projetado)", f"{margem_estoque_pct:.2f}%")

    st.markdown("---")
    st.subheader("📋 Histórico Recente de Vendas")
    if not df_vendas.empty:
        st.dataframe(df_vendas.sort_values(by="data_hora", ascending=False), use_container_width=True)
    else:
        st.info("Nenhuma venda registrada até o momento.")

# ---------------------------------------------------------
# ABA 2: ESTOQUE E PREÇOS
# ---------------------------------------------------------
elif menu == "📦 Estoque & Preços":
    st.title("📦 Gerenciamento de Estoque e Margens")
    
    if not df_estoque.empty:
        # Recalcular a coluna % Margem Lucro sobre o Custo na exibição
        df_estoque['margem_porcentagem'] = df_estoque.apply(
            lambda row: round(((row['preco_venda_unitario'] - row['custo_total_unitario']) / row['custo_total_unitario']) * 100, 2)
            if row['custo_total_unitario'] > 0 else 0.0, axis=1
        )
        
        st.caption("💡 O **Preço de Venda (R$)** reflete 150% de lucro sobre o custo total. Altere os valores se desejar e clique em Salvar.")
        
        df_editavel = st.data_editor(
            df_estoque,
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
            use_container_width=True
        )

        if st.button("💾 Salvar Alterações nos Preços", use_container_width=True):
            salvar_dados(df_editavel, df_vendas)
            st.toast("Preços e margens atualizados!", icon="✅")
            st.rerun()
    else:
        st.info("O estoque está vazio. Importe um pedido em CSV para começar.")

# ---------------------------------------------------------
# ABA 3: REGISTRAR VENDA (PDV)
# ---------------------------------------------------------
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

# ---------------------------------------------------------
# ABA 4: IMPORTAR PEDIDO (CSV)
# ---------------------------------------------------------
elif menu == "📥 Importar Pedido (CSV)":
    st.title("📥 Importar Pedido de Fornecedor")
    st.caption("Suba o arquivo CSV com a lista de compras para atualizar seu estoque automaticamente.")
    
    arquivo_upload = st.file_uploader("Selecione o arquivo CSV do pedido", type=["csv"])
    
    if arquivo_upload is not None:
        if st.button("🚀 Processar Pedido", use_container_width=True):
            with st.spinner("Processando itens, calculando frete e gerando preços sugeridos (150% de lucro)..."):
                df_estoque, sucesso, qtd_itens, frete = processar_csv_upload(arquivo_upload, df_estoque)
                
            if sucesso:
                salvar_dados(df_estoque, df_vendas)
                st.success("✅ Pedido processado e adicionado ao estoque!")
                st.toast("Estoque atualizado com sucesso!", icon="📦")
                
                c1, c2 = st.columns(2)
                c1.metric("Itens Processados", qtd_itens)
                c2.metric("Frete Rateado Detectado", f"R$ {frete:.2f}")
                
                st.balloons()
