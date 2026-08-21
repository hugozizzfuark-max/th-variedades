import re

def limpar_nome_produto(nome):
    """
    Remove números soltos ou marcadores do início do nome 
    (ex: '1 SABONETE...' vira 'SABONETE...')
    """
    nome_limpo = str(nome).strip()
    # Remove prefixos como '1 ', '1(UN)', '1 X ' do início do nome
    nome_limpo = re.sub(r'^\d+\s*(\(un\))?\s*(x)?\s*', '', nome_limpo, flags=re.IGNORECASE)
    return nome_limpo.strip()

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
                st.error(f"Coluna obrigatória '{col}' não foi encontrada no arquivo CSV.")
                return df_estoque, False

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
            # Limpa o nome do produto antes da busca
            nome_bruto = str(row['nome_produto'])
            nome = limpar_nome_produto(nome_bruto)
            
            qtd = row['quantidade']
            custo_unit = row['preco_custo_unitario']
            frete_unit = row['frete_unitario']
            custo_tot_unit = row['custo_total_unitario']

            # Compara nomes padronizados/limpos
            match_index = df_estoque[
                df_estoque['nome_produto'].apply(normalizar_texto) == normalizar_texto(nome)
            ].index

            if len(match_index) > 0:
                # PRODUTO REPETIDO: Soma a quantidade no mesmo SKU
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
                df_estoque.at[idx, 'ultimo_pedido_id'] = id_pedido
            else:
                # PRODUTO NOVO: Cria SKU
                novo_sku = f"TH-{len(df_estoque) + 1:03d}"
                novo_item = {
                    'sku': novo_sku,
                    'nome_produto': nome,
                    'quantidade_estoque': qtd,
                    'preco_custo_unitario': round(custo_unit, 2),
                    'frete_unitario': round(frete_unit, 2),
                    'custo_total_unitario': round(custo_tot_unit, 2),
                    'preco_venda_unitario': 0.0,
                    'ultimo_pedido_id': id_pedido
                }
                df_estoque = pd.concat([df_estoque, pd.DataFrame([novo_item])], ignore_index=True)

        return df_estoque, True
    except Exception as e:
        st.error(f"Erro ao processar o arquivo: {e}")
        return df_estoque, False
