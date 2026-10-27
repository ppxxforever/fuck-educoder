#include <bits/stdc++.h>
using namespace std;

typedef struct{
	char no[20];   								//书号
	char name[100]; 							//书名
	float price;   								//价格
}Book;

typedef struct{
	Book *elem; 								//指向数组的指针
	int length; 								//数组的长度
}SqList;

void InitList(SqList &L){   							
//使用动态内存分配new进行初始化
	L.elem = new Book[1000];
	L.length = 0;
}

void FreeList(SqList &L){
//释放内存
	delete[] L.elem;
	L.elem = NULL;
	L.length = 0;
}

void ReadFile(SqList &L, string filepath){ 
//从文件中读取图书信息，将其按顺序存入L.elem指向的数组中，同时统计图书总数存入L.length中
	ifstream fin(filepath.c_str());
	if(!fin.is_open()) return;
	L.length = 0;
	while(fin >> L.elem[L.length].no >> L.elem[L.length].name >> L.elem[L.length].price){
		L.length++;
	}
	fin.close();
}

int main(){
	SqList L;
	InitList(L);
	ReadFile(L, "book.txt");
	cout << L.length << endl;
	FreeList(L);
	return 0;
}