#include <bits/stdc++.h>
using namespace std;

typedef struct{
	char no[20];
	char name[100];
	float price;
}Book;

typedef struct{
	Book *elem;
	int length;
}SqList;

void InitList(SqList &L){
	L.elem = new Book[1000];
	L.length = 0;
}

void FreeList(SqList &L){
	delete[] L.elem;
	L.elem = NULL;
	L.length = 0;
}

void ReadFile(SqList &L, string filepath){
	ifstream fin(filepath.c_str());
	if(!fin.is_open()){
		return;
	}
	string line;
	for(int i = 0; i < 2; i++){
		getline(fin, line);
		cout << line << endl;
	}
	while(fin >> L.elem[L.length].no >> L.elem[L.length].name >> L.elem[L.length].price){
		cout << L.elem[L.length].no << " " << L.elem[L.length].name << " " << L.elem[L.length].price << endl;
		L.length++;
	}
	fin.close();
}

int main(){
	SqList L;
	InitList(L);
	ReadFile(L, "book.txt");
	FreeList(L);
	return 0;
}