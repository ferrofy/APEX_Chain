const API = "http://127.0.0.1:5000"

async function Load_Data() {

    let Blocks_Res = await fetch(API + "/blocks")
    let Blocks = await Blocks_Res.json()

    document.getElementById("Total_Blocks").innerText = Blocks.length
    document.getElementById("Total_Tx").innerText = Blocks.length

    let Block_List = document.getElementById("Blocks_List")
    let Tx_List = document.getElementById("Tx_List")

    Block_List.innerHTML = ""
    Tx_List.innerHTML = ""

    Blocks.slice(-5).reverse().forEach(Block => {

        let B = document.createElement("div")
        B.className = "Block"
        B.innerHTML = `
            <b>Block #${Block.Index}</b><br>
            Hash: ${Block.Hash.substring(0,20)}...
        `
        Block_List.appendChild(B)

        let T = document.createElement("div")
        T.className = "Tx"
        T.innerHTML = `
            Tx: ${Block.Tx_Id}<br>
            Data: ${Block.Data}
        `
        Tx_List.appendChild(T)
    })
}

async function Search_Data() {

    let Value = document.getElementById("Search_Input").value

    let Res = await fetch(API + "/tx/" + Value)

    if (Res.status !== 200) {
        document.getElementById("Search_Result").innerHTML = "Not Found"
        return
    }

    let Data = await Res.json()

    document.getElementById("Search_Result").innerHTML = `
        <div class="Block">
            <h3>Block #${Data.Index}</h3>
            <p>Tx: ${Data.Tx_Id}</p>
            <p>Data: ${Data.Data}</p>
            <p>Hash: ${Data.Hash}</p>
        </div>
    `
}

Load_Data()